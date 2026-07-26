"""speech_to_text.pipeline —— ASR 转录编排（引擎选择 / 降级 / VAD 并行 / SRT 落盘）。

设计依据：design D2（引擎抽象与选择策略）/ D3（VAD 分段并行）/ D8（并发预算），
spec speech-to-text 全部 Requirement，CONTRACT §6.2 接口签名。

对外入口（CONTRACT §6.2 权威）::

    def transcribe(ctx, audio_rel_path, srt_out_rel_path, asr_config: AsrConfig) -> str

辅助与可测入口：
- ``transcribe_audio(...)`` —— 选引擎（含在线降级）+ VAD 并行 + 偏移拼回，返回 ``list[Cue]``。
- ``transcribe_to_srt(audio_path, asr_config, on_progress=None) -> str`` —— 返回 SRT 文本（不落盘）。

关键不变量（spec）：
1. 输入文件不存在 → 抛错且 MUST NOT 产出空 SRT。
2. SRT 时间戳单调递增、覆盖完整时长（``sanitize_cues`` + 偏移拼回）。
3. 字幕一律 ASR，无 ASR 结果段不伪造（空 Cue 列表 → 空 SRT）。
4. 在线降级 MUST 写结构化日志（原因 / 原引擎 / 目标引擎 / 时间戳）。
5. 所有引擎均不可用 → 抛「无可用 ASR 引擎」，MUST NOT 返回部分 SRT。
6. VAD 切分与拼合对调用方透明（调用方只见一份完整 SRT）。
"""
from __future__ import annotations

import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .engine import (
    REASON_MODEL_MISSING,
    AsrEngine,
    AsrError,
    CancelledError,
    Cue,
    ProgressCallback,
    cues_to_srt,
    get_audio_duration_seconds,
    sanitize_cues,
)
from .asrtools import AsrToolsEngine
from .external import ExternalAsrEngine
from .vad import AudioSegment, split_audio_by_silence
from .whisper_local import WhisperCppEngine

# 日志：优先走内核门面（design D6），内核未就绪时回退到 utils.logger（兼容单测/独立运行）
try:  # pragma: no cover - 仅取决于内核是否就绪
    from src.core.kernel import logger as _logger
except Exception:  # pragma: no cover
    from src.utils import logger as _logger

_LOGGER = logging.getLogger("speech_to_text.pipeline")

# 引擎名常量（与 settings 的 asr.engine 取值一致）
ENGINE_ASRTOOLS = "asrtools"
ENGINE_WHISPER = "whisper_cpp"
ENGINE_EXTERNAL = "external"

STRATEGY_ONLINE_FIRST = "online_first"
STRATEGY_SINGLE = "single"

# 日志回调签名：(level: str, line: str) -> None（对接 DAG ctx.emit_log）
LogCallback = Callable[[str, str], None]
# 取消检查签名：() -> bool（对接 DAG ctx.cancel.is_cancelled）
CancelCheck = Callable[[], bool]


@dataclass
class AsrConfig:
    """ASR 引擎与策略配置（镜像 settings 的 ``asr.*`` 命名空间）。

    所有在线/本地/外部引擎参数集中于此，由 DAG 节点从 SQLite settings 快照构造后传入。
    """

    strategy: str = STRATEGY_ONLINE_FIRST      # online_first / single
    engine: str = ENGINE_ASRTOOLS               # single 模式指定的引擎
    # 在线必剪云接口(bcut=必剪 / jianying=剪映)
    asrtools_provider: str = "bcut"             # bcut(必剪) / jianying(剪映)
    asrtools_sign_endpoint: str = "https://asrtools-update.bkfeng.top/sign"
    asrtools_timeout: float = 120.0
    # 本地 whisper.cpp（CPU + int8）
    whisper_model_path: str = ""
    whisper_binary: str = ""
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_language: str = "zh"
    # 外部 endpoint
    external_endpoint: str = ""
    external_timeout: float = 120.0
    external_api_key: str = ""
    # VAD 与并发（design D3 / D8）
    vad_threshold_seconds: float = 300.0         # > 5 分钟才触发分段
    vad_target_segment_seconds: Optional[float] = None
    concurrency: int = 1
    # 单次 HTTP/转写超时上限（用于 VAD 分段内调用）
    request_timeout: float = 120.0

    @classmethod
    def from_settings(cls, settings: dict) -> "AsrConfig":
        """从 SQLite settings 快照（``asr.*`` 命名空间）构造。

        ``settings`` 可为扁平 dict（``{"asr.engine": ..., "asr.config": "{...}"}``）。
        ``asr.config`` 为 JSON 串/对象，承载引擎专属参数（endpoint / 模型路径 等）。
        """
        engine = str(settings.get("asr.engine", ENGINE_ASRTOOLS))
        strategy = str(settings.get("asr.strategy", STRATEGY_ONLINE_FIRST))
        raw_cfg = settings.get("asr.config")
        cfg: dict = {}
        if isinstance(raw_cfg, str):
            try:
                cfg = json.loads(raw_cfg) if raw_cfg.strip() else {}
            except ValueError:
                cfg = {}
        elif isinstance(raw_cfg, dict):
            cfg = raw_cfg

        def _cfg_str(key, default=""):
            v = cfg.get(key, default)
            return "" if v is None else str(v)

        return cls(
            strategy=strategy if strategy in (STRATEGY_ONLINE_FIRST, STRATEGY_SINGLE) else STRATEGY_ONLINE_FIRST,
            engine=engine if engine in (ENGINE_ASRTOOLS, ENGINE_WHISPER, ENGINE_EXTERNAL) else ENGINE_ASRTOOLS,
            asrtools_provider=str(cfg.get("asrtools_provider", "bcut")) or "bcut",
            asrtools_sign_endpoint=_cfg_str("asrtools_sign_endpoint", "https://asrtools-update.bkfeng.top/sign"),
            asrtools_timeout=float(cfg.get("asrtools_timeout", 120.0) or 120.0),
            whisper_model_path=_cfg_str("whisper_model_path") or _cfg_str("model_path"),
            whisper_binary=_cfg_str("whisper_binary") or _cfg_str("binary"),
            whisper_device=str(cfg.get("whisper_device", "cpu") or "cpu"),
            whisper_compute_type=str(cfg.get("whisper_compute_type", "int8") or "int8"),
            whisper_language=str(cfg.get("whisper_language", "zh") or "zh"),
            external_endpoint=_cfg_str("external_endpoint") or _cfg_str("endpoint"),
            external_timeout=float(cfg.get("external_timeout", 120.0) or 120.0),
            external_api_key=_cfg_str("external_api_key") or _cfg_str("api_key"),
            vad_threshold_seconds=float(cfg.get("vad_threshold_seconds", 300.0) or 300.0),
            vad_target_segment_seconds=(
                float(cfg["vad_target_segment_seconds"]) if cfg.get("vad_target_segment_seconds") else None
            ),
            concurrency=max(1, int(cfg.get("concurrency", settings.get("concurrency.max", 1)) or 1)),
            request_timeout=float(cfg.get("request_timeout", 120.0) or 120.0),
        )


# --------------------------------------------------------------------------- #
# 引擎构建与策略解析
# --------------------------------------------------------------------------- #


def build_engines(config: AsrConfig) -> dict[str, AsrEngine]:
    """按配置实例化全部引擎（不预检可用性，运行时惰性判定）。"""
    return {
        ENGINE_ASRTOOLS: AsrToolsEngine(
            provider=config.asrtools_provider,
            sign_endpoint=config.asrtools_sign_endpoint,
            timeout=config.asrtools_timeout,
        ),
        ENGINE_WHISPER: WhisperCppEngine(
            model_path=config.whisper_model_path,
            binary=config.whisper_binary,
            device=config.whisper_device,
            compute_type=config.whisper_compute_type,
            language=config.whisper_language,
        ),
        ENGINE_EXTERNAL: ExternalAsrEngine(
            endpoint=config.external_endpoint,
            timeout=config.external_timeout,
            api_key=config.external_api_key,
        ),
    }


def resolve_engine_order(config: AsrConfig) -> list[str]:
    """按策略返回「尝试顺序」的引擎名列表。

    - ``online_first``（默认，design D2）：在线引擎在前（AsrTools 默认首选；如配置了
      external 也作为在线候选），本地 whisper.cpp 兜底。
    - ``single``：仅 ``config.engine`` 指定的那一种，**不降级**。
    """
    if config.strategy == STRATEGY_SINGLE:
        return [config.engine] if config.engine in (ENGINE_ASRTOOLS, ENGINE_WHISPER, ENGINE_EXTERNAL) else [ENGINE_ASRTOOLS]
    # online_first
    order: list[str] = []
    if config.engine == ENGINE_EXTERNAL:
        order.append(ENGINE_EXTERNAL)
    if ENGINE_ASRTOOLS not in order:
        order.append(ENGINE_ASRTOOLS)
    if config.engine == ENGINE_EXTERNAL and ENGINE_EXTERNAL not in order:
        order.append(ENGINE_EXTERNAL)
    # 兜底：本地 whisper（始终放最后）
    if ENGINE_WHISPER not in order:
        order.append(ENGINE_WHISPER)
    return order


# --------------------------------------------------------------------------- #
# 降级事件日志（spec「在线引擎降级与日志记录」）
# --------------------------------------------------------------------------- #


def _emit_degradation(
    from_engine: str,
    to_engine: str,
    reason: str,
    *,
    status_code: Optional[int] = None,
    task_id: str = "",
    on_log: Optional[LogCallback] = None,
) -> None:
    """写一条结构化降级事件日志（原因 / 原引擎 / 目标引擎 / 时间戳）。"""
    event = {
        "event": "asr_degradation",
        "from": from_engine,
        "to": to_engine,
        "reason": reason,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    if status_code is not None:
        event["status_code"] = status_code
    if task_id:
        event["task_id"] = task_id
    line = json.dumps(event, ensure_ascii=False)
    _logger.warning("ASR 在线降级：%s", line, extra={"extra_data": event})
    if on_log:
        on_log("warn", f"[ASR 降级] {from_engine} → {to_engine}（原因：{reason}）")


# --------------------------------------------------------------------------- #
# 核心：引擎选择 + 降级（单段转录）
# --------------------------------------------------------------------------- #


class _EngineResolver:
    """跨 VAD 分段共享的引擎选择器：记住已失败引擎，避免对失效在线引擎重复请求。

    线程安全（VAD 各段在并行线程中调用 ``transcribe``）。
    """

    def __init__(
        self,
        engines: dict[str, AsrEngine],
        order: list[str],
        *,
        strategy: str,
        task_id: str = "",
        on_log: Optional[LogCallback] = None,
        is_cancelled: Optional[CancelCheck] = None,
    ) -> None:
        self._engines = engines
        self._order = order
        self._strategy = strategy
        self._task_id = task_id
        self._on_log = on_log
        self._is_cancelled = is_cancelled
        self._failed: set[str] = set()
        self._attempted: list[str] = []  # 实际尝试过的引擎名（按顺序，含成功者）
        self._lock = threading.Lock()
        # 记录本次 resolver 最终成功的引擎，供后续段直接命中（避免每次都从头试）
        self._preferred: Optional[str] = None

    def transcribe(
        self, audio_path: str, on_progress: Optional[ProgressCallback] = None
    ) -> list[Cue]:
        """按顺序尝试引擎，首个可用引擎的转录结果胜出；在线失败写降级日志后转下一个。"""
        # 优先复用已成功的引擎
        with self._lock:
            order = list(self._order)
            preferred = self._preferred
        if preferred and preferred in self._engines and preferred not in self._failed:
            order = [preferred] + [e for e in order if e != preferred]

        last_error: Optional[AsrError] = None
        for idx, name in enumerate(order):
            if self._is_cancelled and self._is_cancelled():
                raise CancelledError("ASR 转录被取消")
            with self._lock:
                if name in self._failed:
                    continue
            engine = self._engines.get(name)
            if engine is None:
                continue
            with self._lock:
                if name not in self._attempted:
                    self._attempted.append(name)
            try:
                cues = engine.transcribe(audio_path, on_progress=on_progress)
                with self._lock:
                    self._preferred = name
                return cues
            except CancelledError:
                raise
            except AsrError as e:
                last_error = e
                with self._lock:
                    self._failed.add(name)
                # single 策略：不降级，直接以该引擎失败结束
                if self._strategy == STRATEGY_SINGLE:
                    raise
                # online_first：寻找下一个非 failed 引擎写降级日志
                nxt = self._next_available(name, order)
                if nxt is None:
                    break
                _emit_degradation(
                    name, nxt, e.reason,
                    status_code=e.status_code, task_id=self._task_id, on_log=self._on_log,
                )
            except Exception as e:  # 引擎实现意外异常，归一为 AsrError 后降级
                last_error = AsrError(f"引擎 {name} 异常：{e}", reason="unknown", engine=name)
                with self._lock:
                    self._failed.add(name)
                if self._strategy == STRATEGY_SINGLE:
                    raise last_error
                nxt = self._next_available(name, order)
                if nxt is None:
                    break
                _emit_degradation(name, nxt, "unknown", task_id=self._task_id, on_log=self._on_log)

        # 全部不可用
        with self._lock:
            attempted = list(self._attempted)
        tried = ",".join(attempted) or "(无)"
        raise AsrError(
            f"无可用 ASR 引擎（已尝试：{tried}）",
            reason=REASON_MODEL_MISSING, engine="speech_to_text",
        )

    def _next_available(self, after: str, order: list[str]) -> Optional[str]:
        with self._lock:
            for name in order:
                if name == after:
                    continue
                if name in self._failed:
                    continue
                if name in self._engines:
                    return name
        return None


# --------------------------------------------------------------------------- #
# 核心：整段转录 + VAD 分段并行
# --------------------------------------------------------------------------- #


def transcribe_audio(
    audio_path: str,
    config: AsrConfig,
    *,
    on_progress: Optional[ProgressCallback] = None,
    on_log: Optional[LogCallback] = None,
    is_cancelled: Optional[CancelCheck] = None,
    task_id: str = "",
    work_dir: Optional[str] = None,
) -> list[Cue]:
    """选引擎（含在线降级）+ VAD 分段并行 + 时间戳偏移拼回，返回完整 ``list[Cue]``。

    分段与拼合对调用方透明（design D3）。短音频（≤ ``vad_threshold_seconds``）不分段、
    直接整段转录。
    """
    if not os.path.exists(audio_path):
        raise AsrError(
            f"音频文件不存在：{audio_path}", reason="invalid_response", engine="speech_to_text"
        )

    engines = build_engines(config)
    order = resolve_engine_order(config)
    resolver = _EngineResolver(
        engines, order,
        strategy=config.strategy, task_id=task_id,
        on_log=on_log, is_cancelled=is_cancelled,
    )

    duration = get_audio_duration_seconds(audio_path)
    threshold = config.vad_threshold_seconds

    # 无法探知时长或短于阈值 → 整段转录（MUST NOT 误切，spec「短音频不触发分段」）
    if duration is None or duration <= threshold:
        if on_log:
            on_log("info", "音频较短或时长未知，整段转录（不触发 VAD 分段）")
        return resolver.transcribe(audio_path, on_progress=on_progress)

    # 长音频 → VAD 静音切分 + 并行转录
    if work_dir is None:
        work_dir = os.path.join(os.path.dirname(os.path.abspath(audio_path)), f".asr_segments_{os.getpid()}")
    if on_log:
        on_log("info", f"音频较长（{duration:.0f}s），触发 VAD 静音切分并行转录")
    segments = split_audio_by_silence(
        audio_path, duration, work_dir,
        max_segment_sec=threshold,
        target_segment_sec=config.vad_target_segment_seconds,
    )

    # 单段（VAD 未能切出多段）→ 退化为整段
    if len(segments) <= 1:
        return resolver.transcribe(audio_path, on_progress=on_progress)

    cues = _transcribe_segments_parallel(
        segments, resolver, config, on_progress, on_log, is_cancelled
    )
    return cues


def _transcribe_segments_parallel(
    segments: list[AudioSegment],
    resolver: _EngineResolver,
    config: AsrConfig,
    on_progress: Optional[ProgressCallback],
    on_log: Optional[LogCallback],
    is_cancelled: Optional[CancelCheck],
) -> list[Cue]:
    """对 VAD 各段并行调用引擎，段内时间戳叠加段起始偏移，拼回单调 SRT。"""
    if is_cancelled and is_cancelled():
        raise CancelledError("ASR 转录被取消")

    total = len(segments)
    workers = max(1, min(config.concurrency, total))
    # 每段独立进度，按完成数映射整体百分比
    done_state = {"done": 0}
    progress_lock = threading.Lock()

    def _seg_progress_factory():
        def _cb(percent: int, message: Optional[str] = None) -> None:
            return None
        return _cb

    results: dict[int, list[Cue]] = {}

    def _worker(idx: int, seg: AudioSegment) -> tuple[int, list[Cue]]:
        if is_cancelled and is_cancelled():
            raise CancelledError("ASR 转录被取消")
        seg_cues = resolver.transcribe(seg.path, on_progress=_seg_progress_factory())
        # 时间戳偏移拼回（design D3：段从 300s 起、段内 10s → 310s）
        offset = seg.start_offset
        applied = [
            Cue(start=c.start + offset, end=c.end + offset, text=c.text)
            for c in seg_cues
        ]
        return idx, applied

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_idx = {pool.submit(_worker, i, seg): i for i, seg in enumerate(segments)}
            for fut in as_completed(future_to_idx):
                idx, applied = fut.result()
                results[idx] = applied
                with progress_lock:
                    done_state["done"] += 1
                    if on_progress:
                        on_progress(int(done_state["done"] / total * 100), f"已转录 {done_state['done']}/{total} 段")
                    if on_log:
                        on_log("info", f"分段转录完成：{done_state['done']}/{total}（起始偏移 {segments[idx].start_offset:.0f}s）")
    finally:
        # 清理临时分段文件（保留原音频）
        for seg in segments:
            try:
                if seg.path and os.path.exists(seg.path) and seg.path != segments[0].path:
                    # 仅删除我们抽出的临时 WAV（非原音频）
                    p = os.path.abspath(seg.path)
                    if p.startswith(os.path.abspath(os.path.dirname(seg.path))) and os.path.basename(p).startswith("segment_"):
                        os.remove(seg.path)
            except OSError:
                pass

    if is_cancelled and is_cancelled():
        raise CancelledError("ASR 转录被取消")

    # 按段顺序合并 → sanitize 保证单调、无重叠/空洞
    merged: list[Cue] = []
    for idx in sorted(results.keys()):
        merged.extend(results[idx])
    return sanitize_cues(merged)


# --------------------------------------------------------------------------- #
# 便捷入口：返回 SRT 文本（不落盘，供单测/独立调用）
# --------------------------------------------------------------------------- #


def transcribe_to_srt(
    audio_path: str,
    asr_config: AsrConfig,
    *,
    on_progress: Optional[ProgressCallback] = None,
    on_log: Optional[LogCallback] = None,
    is_cancelled: Optional[CancelCheck] = None,
) -> str:
    """转写音频并返回标准 SRT 文本（不写文件）。

    输入不存在时抛错（不产出空 SRT）；纯静音段返回空串（spec 允许如实省略）。
    """
    cues = transcribe_audio(
        audio_path, asr_config,
        on_progress=on_progress, on_log=on_log, is_cancelled=is_cancelled,
    )
    return cues_to_srt(cues)


# --------------------------------------------------------------------------- #
# CONTRACT §6.2 DAG 节点入口
# --------------------------------------------------------------------------- #


def _resolve_data_root(ctx) -> Path:
    """优先 ctx.data_root，其次环境变量 ``DATA_ROOT``，再次默认 ``backend/data``。"""
    dr = getattr(ctx, "data_root", None)
    if dr is not None:
        return Path(dr)
    env = os.environ.get("DATA_ROOT")
    if env:
        return Path(env)
    # 默认 backend/data（CONTRACT §2 约定）
    return Path(__file__).resolve().parents[2] / "data"


def _resolve_abs(data_root: Path, rel_or_abs: str) -> Path:
    p = Path(rel_or_abs)
    if p.is_absolute():
        return p
    return data_root / p


def _ctx_callbacks(ctx):
    """从 DAG ``NodeContext`` 安全抽取回调；ctx 为 None 时全部 no-op。"""
    if ctx is None:
        return (None, None, None)

    def _on_progress(percent: int, message: Optional[str] = None) -> None:
        emit = getattr(ctx, "emit_progress", None)
        if callable(emit):
            try:
                emit(int(percent), message)
            except Exception:  # SSE/落库异常不得中断 ASR
                _LOGGER.debug("emit_progress 失败，已忽略", exc_info=True)

    def _on_log(level: str, line: str) -> None:
        emit = getattr(ctx, "emit_log", None)
        if callable(emit):
            try:
                emit(level, line)
            except Exception:
                _LOGGER.debug("emit_log 失败，已忽略", exc_info=True)

    def _is_cancelled() -> bool:
        cancel = getattr(ctx, "cancel", None)
        if cancel is None:
            return False
        chk = getattr(cancel, "is_cancelled", None)
        if callable(chk):
            try:
                return bool(chk())
            except Exception:
                return False
        return False

    return (_on_progress, _on_log, _is_cancelled)


def transcribe(
    ctx,
    audio_rel_path: str,
    srt_out_rel_path: str,
    asr_config: AsrConfig,
) -> str:
    """ASR DAG 节点入口（CONTRACT §6.2 权威签名）。

    流程：
    1. 解析 ``audio_rel_path`` 为绝对路径（相对则基于 ``DATA_ROOT``）；不存在则抛错，
       **MUST NOT 创建空 SRT**（spec「输入文件不存在时报错」）。
    2. 选引擎（含在线降级）+ VAD 并行 + 偏移拼回 → ``list[Cue]``。
    3. ``cues_to_srt`` 写标准 SRT 到 ``srt_out_rel_path``（解析为绝对路径，确保父目录）。
    4. ``ctx.register_product('srt', srt_out_rel_path, size_bytes)`` 登记产物。
    5. 返回 SRT 相对路径。

    Raises:
        AsrError: 输入缺失 / 无可用引擎 / 转写失败。
        CancelledError: 被取消。
    """
    on_progress, on_log, is_cancelled = _ctx_callbacks(ctx)
    data_root = _resolve_data_root(ctx)

    audio_abs = _resolve_abs(data_root, audio_rel_path)
    if not audio_abs.exists():
        # spec：MUST NOT 创建空的 SRT 文件
        raise AsrError(
            f"ASR 输入音频不存在：{audio_rel_path}", reason="invalid_response", engine="speech_to_text"
        )

    task = getattr(ctx, "task", None)
    task_id = getattr(task, "task_id", "") or getattr(task, "id", "") or ""

    # 临时分段工作区：data/temp/<task_id>/asr_segments（CONTRACT §2 temp/ 隔离）
    work_temp = getattr(ctx, "work_temp", None)
    if work_temp is not None:
        work_dir = str(Path(work_temp) / "asr_segments")
    else:
        work_dir = str(data_root / "temp" / (task_id or "anon") / "asr_segments")

    cues = transcribe_audio(
        str(audio_abs),
        asr_config,
        on_progress=on_progress,
        on_log=on_log,
        is_cancelled=is_cancelled,
        task_id=task_id,
        work_dir=work_dir,
    )

    srt_text = cues_to_srt(cues)
    srt_abs = _resolve_abs(data_root, srt_out_rel_path)
    srt_abs.parent.mkdir(parents=True, exist_ok=True)
    # 先写临时文件再 rename，避免半成品（写过程被取消时不残留损坏 SRT）
    tmp_abs = srt_abs.with_suffix(srt_abs.suffix + ".partial")
    with open(tmp_abs, "w", encoding="utf-8") as f:
        f.write(srt_text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_abs, srt_abs)

    size_bytes = srt_abs.stat().st_size
    register = getattr(ctx, "register_product", None)
    if callable(register):
        try:
            # 登记相对 DATA_ROOT 的 POSIX 相对路径（CONTRACT §0.4）
            try:
                rel_for_db = srt_abs.relative_to(data_root).as_posix()
            except ValueError:
                rel_for_db = srt_out_rel_path
            register("srt", rel_for_db, size_bytes)
        except Exception:
            _LOGGER.debug("register_product 失败，已忽略", exc_info=True)

    if on_log:
        on_log("ok", f"ASR 转写完成，SRT 已写入（{len(cues)} 条字幕，{size_bytes} 字节）")
    # 返回相对 DATA_ROOT 的 POSIX 路径（落库形态）
    try:
        return srt_abs.relative_to(data_root).as_posix()
    except ValueError:
        return srt_out_rel_path
