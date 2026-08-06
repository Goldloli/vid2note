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
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .engine import (
    REASON_MODEL_MISSING,
    REASON_RATE_LIMITED,
    AsrEngine,
    AsrError,
    CancelledError,
    Cue,
    ProgressCallback,
    cues_to_srt,
    get_audio_duration_seconds,
    sanitize_cues,
)
from .bcut import BcutEngine
from . import asr_cache
from . import bcut_budget
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
ENGINE_BCUT = "bcut"
ENGINE_WHISPER = "whisper_cpp"
ENGINE_EXTERNAL = "external"

STRATEGY_ONLINE_FIRST = "online_first"
STRATEGY_SINGLE = "single"

# 日志回调签名：(level: str, line: str) -> None（对接 DAG ctx.emit_log）
LogCallback = Callable[[str, str], None]
# 取消检查签名：() -> bool（对接 DAG ctx.cancel.is_cancelled）
CancelCheck = Callable[[], bool]

# faster-whisper 的 CPU 推理会占满宿主机核心。槽位按 resolver（即任务）生命周期
# 持有，避免多个长任务按分段轮流抢占，导致每条任务一起变慢。
_LOCAL_TASK_SLOT = threading.BoundedSemaphore(1)
# 多任务的首个真实 bcut 分段串行探测，防止远端额度耗尽时同时撞 412。
_BCUT_PROBE_LOCK = threading.Lock()


@dataclass
class AsrConfig:
    """ASR 引擎与策略配置（镜像 settings 的 ``asr.*`` 命名空间）。

    所有在线/本地/外部引擎参数集中于此，由 DAG 节点从运行时设置快照构造后传入。
    """

    strategy: str = STRATEGY_ONLINE_FIRST      # online_first / single
    engine: str = ENGINE_BCUT                    # single 模式指定的引擎
    bcut_timeout: float = 120.0
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
    # 旧字段仅保留给代码级兼容；新设置分别使用在线/本地档案。
    vad_target_segment_seconds: Optional[float] = None
    concurrency: Optional[int] = None
    online_target_segment_seconds: float = 280.0
    local_target_segment_seconds: float = 120.0
    online_concurrency: int = 3
    local_concurrency: int = 1
    online_audio_format: str = "mp3"
    online_audio_bitrate_kbps: int = 64
    # 单次 HTTP/转写超时上限（用于 VAD 分段内调用）
    request_timeout: float = 120.0
    # bcut 在线：轮询退避起步间隔 / 最大等待 / crc32 结果缓存
    query_interval: float = 1.0
    query_max_wait: float = 600.0
    cache_enabled: bool = True
    cache_dir: str = ""

    def effective_concurrency(self, *, online: bool) -> int:
        if self.concurrency is not None:
            return max(1, min(3, int(self.concurrency)))
        value = self.online_concurrency if online else self.local_concurrency
        return max(1, min(3, int(value)))

    def effective_target_segment_seconds(self, *, online: bool) -> float:
        if self.vad_target_segment_seconds is not None:
            return float(self.vad_target_segment_seconds)
        return float(
            self.online_target_segment_seconds if online else self.local_target_segment_seconds
        )

    @classmethod
    def from_settings(cls, settings: dict) -> "AsrConfig":
        """从运行时设置快照（``asr.*`` 命名空间）构造。

        ``settings`` 可为扁平 dict（``{"asr.engine": ..., "asr.config": "{...}"}``）。
        ``asr.config`` 为 JSON 串/对象，承载引擎专属参数（endpoint / 模型路径 等）。
        """
        engine = str(settings.get("asr.engine", ENGINE_BCUT))
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

        def _cfg_bool(key, default=True):
            value = cfg.get(key, default)
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() not in {"false", "0", "no", "off"}

        legacy_concurrency = cfg.get("concurrency")
        legacy_target = cfg.get("vad_target_segment_seconds")
        default_data_root = os.environ.get("DATA_ROOT") or str(
            Path(__file__).resolve().parents[2] / "data"
        )
        online_format = str(cfg.get("online_audio_format", "mp3") or "mp3").lower()
        if online_format not in {"mp3", "wav"}:
            online_format = "mp3"
        return cls(
            strategy=strategy if strategy in (STRATEGY_ONLINE_FIRST, STRATEGY_SINGLE) else STRATEGY_ONLINE_FIRST,
            engine=engine if engine in (ENGINE_BCUT, ENGINE_WHISPER, ENGINE_EXTERNAL) else ENGINE_BCUT,
            bcut_timeout=float(cfg.get("bcut_timeout", 120.0) or 120.0),
            whisper_model_path=_cfg_str("whisper_model_path") or _cfg_str("model_path"),
            whisper_binary=_cfg_str("whisper_binary") or _cfg_str("binary"),
            whisper_device=str(cfg.get("whisper_device", "cpu") or "cpu"),
            whisper_compute_type=str(cfg.get("whisper_compute_type", "int8") or "int8"),
            whisper_language=str(cfg.get("whisper_language", "zh") or "zh"),
            external_endpoint=_cfg_str("external_endpoint") or _cfg_str("endpoint"),
            external_timeout=float(cfg.get("external_timeout", 120.0) or 120.0),
            external_api_key=_cfg_str("external_api_key") or _cfg_str("api_key"),
            vad_threshold_seconds=float(cfg.get("vad_threshold_seconds", 300.0) or 300.0),
            online_target_segment_seconds=float(
                cfg.get("online_target_segment_seconds", legacy_target or 280.0) or 280.0
            ),
            local_target_segment_seconds=float(
                cfg.get("local_target_segment_seconds", legacy_target or 120.0) or 120.0
            ),
            online_concurrency=max(1, int(
                cfg.get("online_concurrency", legacy_concurrency or 3) or 3
            )),
            local_concurrency=max(1, int(cfg.get("local_concurrency", 1) or 1)),
            online_audio_format=online_format,
            online_audio_bitrate_kbps=max(32, int(
                cfg.get("online_audio_bitrate_kbps", 64) or 64
            )),
            request_timeout=float(cfg.get("request_timeout", 120.0) or 120.0),
            query_interval=max(0.5, float(cfg.get("query_interval", 1.0) or 1.0)),
            query_max_wait=float(cfg.get("query_max_wait", 600.0) or 600.0),
            cache_enabled=_cfg_bool("cache_enabled", True),
            cache_dir=str(cfg.get("cache_dir", "") or Path(default_data_root) / "asr_cache"),
        )


# --------------------------------------------------------------------------- #
# 引擎构建与策略解析
# --------------------------------------------------------------------------- #


def build_engines(config: AsrConfig) -> dict[str, AsrEngine]:
    """按配置实例化全部引擎（不预检可用性，运行时惰性判定）。"""
    return {
        ENGINE_BCUT: BcutEngine(
            timeout=config.bcut_timeout,
            query_interval=config.query_interval,
            query_max_wait=config.query_max_wait,
            cache_enabled=config.cache_enabled,
            cache_dir=config.cache_dir or None,
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

    - ``online_first``（默认，design D2）：在线引擎在前（bcut 默认首选；如配置了
      external 也作为在线候选），本地 whisper.cpp 兜底。
    - ``single``：仅 ``config.engine`` 指定的那一种，**不降级**。
    """
    if config.strategy == STRATEGY_SINGLE:
        return [config.engine] if config.engine in (ENGINE_BCUT, ENGINE_WHISPER, ENGINE_EXTERNAL) else [ENGINE_BCUT]
    # online_first
    order: list[str] = []
    if config.engine == ENGINE_EXTERNAL:
        order.append(ENGINE_EXTERNAL)
    if ENGINE_BCUT not in order:
        order.append(ENGINE_BCUT)
    if config.engine == ENGINE_EXTERNAL and ENGINE_EXTERNAL not in order:
        order.append(ENGINE_EXTERNAL)
    # 兜底：本地 whisper（始终放最后）
    if ENGINE_WHISPER not in order:
        order.append(ENGINE_WHISPER)
    return order


# 在线引擎失败多为间歇（限流/抖动/服务端 data=null），不应让单段失败永久跳过它，
# 否则一段失败会把后续所有段一起塌方到慢速本地引擎。
_ONLINE_ENGINE_NAMES = frozenset({ENGINE_BCUT, ENGINE_EXTERNAL})


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
        on_rate_limited: Optional[Callable[[], None]] = None,
    ) -> None:
        self._engines = engines
        self._order = order
        self._strategy = strategy
        self._task_id = task_id
        self._on_log = on_log
        self._is_cancelled = is_cancelled
        self._on_rate_limited = on_rate_limited
        self._failed: set[str] = set()
        self._attempted: list[str] = []  # 实际尝试过的引擎名（按顺序，含成功者）
        self._success_counts: dict[str, int] = {}
        self._degradation_count = 0
        self._lock = threading.Lock()
        self._local_semaphore = threading.Semaphore(1)
        self._local_acquire_lock = threading.Lock()
        self._local_slot_acquired = False
        self._local_slot_ever_acquired = False
        self._local_wait_seconds = 0.0
        self._closed = False
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
                if name == ENGINE_WHISPER:
                    self._acquire_local_slot()
                    with self._local_semaphore:
                        cues = engine.transcribe(audio_path, on_progress=on_progress)
                else:
                    cues = engine.transcribe(audio_path, on_progress=on_progress)
                with self._lock:
                    # 只把在线引擎记为 preferred：本地降级成功不锁定 preferred，否则
                    # 一段在线间歇失败会让后续所有段都锁定在慢速本地引擎上
                    if name in _ONLINE_ENGINE_NAMES:
                        self._preferred = name
                    self._success_counts[name] = self._success_counts.get(name, 0) + 1
                return cues
            except CancelledError:
                raise
            except AsrError as e:
                last_error = e
                # 412/429 代表滚动额度或远端限流：本任务剩余分段不再继续撞接口。
                # 其他在线抖动仍按段恢复；本地引擎失败则永久标记。
                first_terminal_failure = True
                if name not in _ONLINE_ENGINE_NAMES or e.reason == REASON_RATE_LIMITED:
                    with self._lock:
                        first_terminal_failure = name not in self._failed
                        self._failed.add(name)
                if (
                    name == ENGINE_BCUT
                    and e.reason == REASON_RATE_LIMITED
                    and first_terminal_failure
                    and self._on_rate_limited is not None
                ):
                    self._on_rate_limited()
                # single 策略：不降级，直接以该引擎失败结束
                if self._strategy == STRATEGY_SINGLE:
                    raise
                # online_first：寻找下一个非 failed 引擎写降级日志
                nxt = self._next_available(name, order)
                if nxt is None:
                    break
                if first_terminal_failure:
                    with self._lock:
                        self._degradation_count += 1
                    _emit_degradation(
                        name, nxt, e.reason,
                        status_code=e.status_code, task_id=self._task_id, on_log=self._on_log,
                    )
            except Exception as e:  # 引擎实现意外异常，归一为 AsrError 后降级
                last_error = AsrError(f"引擎 {name} 异常：{e}", reason="unknown", engine=name)
                if name not in _ONLINE_ENGINE_NAMES:
                    with self._lock:
                        self._failed.add(name)
                if self._strategy == STRATEGY_SINGLE:
                    raise last_error
                nxt = self._next_available(name, order)
                if nxt is None:
                    break
                with self._lock:
                    self._degradation_count += 1
                _emit_degradation(name, nxt, "unknown", task_id=self._task_id, on_log=self._on_log)

        # 全部不可用
        with self._lock:
            attempted = list(self._attempted)
        tried = ",".join(attempted) or "(无)"
        raise AsrError(
            f"无可用 ASR 引擎（已尝试：{tried}）",
            reason=REASON_MODEL_MISSING, engine="speech_to_text",
        )

    def metrics_snapshot(self) -> dict:
        with self._lock:
            return {
                "engine_attempts": list(self._attempted),
                "engine_success_counts": dict(self._success_counts),
                "degradation_count": self._degradation_count,
                "local_slot_acquired": self._local_slot_ever_acquired,
                "local_slot_wait_seconds": round(self._local_wait_seconds, 3),
            }

    def disable_engine(self, name: str) -> None:
        """在发起请求前停用已被共享协调层确认不可用的引擎。"""
        with self._lock:
            self._failed.add(name)

    def is_engine_disabled(self, name: str) -> bool:
        with self._lock:
            return name in self._failed

    def _acquire_local_slot(self) -> None:
        if self._local_slot_acquired:
            return
        with self._local_acquire_lock:
            if self._local_slot_acquired:
                return
            started = time.perf_counter()
            while True:
                if self._is_cancelled and self._is_cancelled():
                    self._local_wait_seconds += time.perf_counter() - started
                    raise CancelledError("等待本地 ASR 执行槽时被取消")
                if _LOCAL_TASK_SLOT.acquire(timeout=0.05):
                    self._local_wait_seconds += time.perf_counter() - started
                    self._local_slot_acquired = True
                    self._local_slot_ever_acquired = True
                    return

    def close(self) -> None:
        """幂等释放任务级本地执行槽；由 ``transcribe_audio`` 的 finally 调用。"""
        with self._local_acquire_lock:
            if self._closed:
                return
            self._closed = True
            if self._local_slot_acquired:
                self._local_slot_acquired = False
                _LOCAL_TASK_SLOT.release()

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
    metrics: Optional[dict] = None,
) -> list[Cue]:
    """选引擎（含在线降级）+ VAD 分段并行 + 时间戳偏移拼回，返回完整 ``list[Cue]``。

    分段与拼合对调用方透明（design D3）。短音频（≤ ``vad_threshold_seconds``）不分段、
    直接整段转录。
    """
    started = time.perf_counter()
    measured = metrics if metrics is not None else {}
    measured.update({
        "schema_version": 1,
        "cache_hit": False,
        "segment_count": 0,
        "worker_count": 0,
        "source_bytes": 0,
        "upload_bytes": 0,
        "split_seconds": 0.0,
        "transcribe_seconds": 0.0,
        "retry_count": 0,
        "bcut_budget_allowed": None,
        "bcut_budget_tracked": None,
        "degradation_count": 0,
        "online_probe_used": False,
        "bcut_cooldown_skipped": False,
        "local_slot_acquired": False,
        "local_slot_wait_seconds": 0.0,
    })
    if not os.path.exists(audio_path):
        raise AsrError(
            f"音频文件不存在：{audio_path}", reason="invalid_response", engine="speech_to_text"
        )

    order = resolve_engine_order(config)
    online_profile = bool(order and order[0] in _ONLINE_ENGINE_NAMES)
    measured["engine_order"] = order
    measured["source_bytes"] = os.path.getsize(audio_path)
    measured["segment_format"] = config.online_audio_format if online_profile else "wav"

    cache_key: Optional[str] = None
    resolver: Optional[_EngineResolver] = None
    engines: dict[str, AsrEngine] = {}
    transcribe_started: Optional[float] = None
    try:
        if config.cache_enabled and config.cache_dir:
            cache_started = time.perf_counter()
            result_profile = json.dumps(
                {
                    "threshold": config.vad_threshold_seconds,
                    "target": config.effective_target_segment_seconds(online=online_profile),
                    "format": measured["segment_format"],
                    "bitrate": config.online_audio_bitrate_kbps if online_profile else None,
                    "external_endpoint": config.external_endpoint,
                    "whisper_model_path": config.whisper_model_path,
                    "whisper_compute_type": config.whisper_compute_type,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            try:
                cache_key = asr_cache.whole_file_cache_key(
                    ",".join(order),
                    audio_path,
                    lang=config.whisper_language,
                    result_profile=result_profile,
                )
                cached = asr_cache.get(config.cache_dir, cache_key)
            except OSError:
                _LOGGER.warning("ASR 整段缓存查询失败，转为冷启动", exc_info=True)
                cached = None
            measured["cache_lookup_seconds"] = round(time.perf_counter() - cache_started, 3)
            if cached is not None:
                measured.update({
                    "cache_hit": True,
                    "segment_count": 0,
                    "worker_count": 0,
                    "audio_duration_seconds": round(max((cue.end for cue in cached), default=0.0), 3),
                    "cue_count": len(cached),
                })
                if on_log:
                    on_log("ok", f"ASR 整段缓存命中，跳过 VAD 与在线转录（{len(cached)} 条字幕）")
                return cached

        engines = build_engines(config)
        resolver = _EngineResolver(
            engines, order,
            strategy=config.strategy, task_id=task_id,
            on_log=on_log, is_cancelled=is_cancelled,
            on_rate_limited=lambda: bcut_budget.mark_rate_limited(
                config.cache_dir or None
            ),
        )

        duration_started = time.perf_counter()
        duration = get_audio_duration_seconds(audio_path)
        measured["duration_probe_seconds"] = round(time.perf_counter() - duration_started, 3)
        measured["audio_duration_seconds"] = round(float(duration or 0.0), 3)
        threshold = config.vad_threshold_seconds

        # bcut 是未承诺 SLA 的公益接口。整项任务开始前按公开参考客户端的滚动窗口
        # 一次性预留预算，避免长视频做到一半才 412，产生前后识别风格不同的混合字幕。
        if order and order[0] == ENGINE_BCUT:
            target = min(
                config.effective_target_segment_seconds(online=True),
                295.0,
            )
            expected_calls = 1 if duration is None or duration <= threshold else max(
                1, math.ceil(float(duration) / max(1.0, target))
            )
            decision = bcut_budget.reserve(
                config.cache_dir or None,
                calls=expected_calls,
                audio_seconds=float(duration or 0.0),
            )
            measured.update({
                f"bcut_budget_{key}": value
                for key, value in decision.to_dict().items()
            })
            if not decision.allowed:
                retry_minutes = math.ceil(decision.retry_after_seconds / 60)
                message = (
                    "bcut 滚动额度不足，整项任务不再使用在线分段"
                    f"（预计 {expected_calls} 次 / {float(duration or 0.0) / 60:.1f} 分钟，"
                    f"约 {retry_minutes} 分钟后恢复）"
                )
                if on_log:
                    on_log("warn", message)
                _LOGGER.warning(message)
                if decision.reason == "remote_rate_limited":
                    measured["bcut_cooldown_skipped"] = True
                if config.strategy == STRATEGY_SINGLE:
                    raise AsrError(
                        message,
                        reason=REASON_RATE_LIMITED,
                        engine=ENGINE_BCUT,
                        status_code=429,
                    )
                order = [name for name in order if name != ENGINE_BCUT]
                online_profile = bool(order and order[0] in _ONLINE_ENGINE_NAMES)
                measured["engine_order"] = order
                measured["segment_format"] = (
                    config.online_audio_format if online_profile else "wav"
                )
                engines = build_engines(config)
                resolver.close()
                resolver = _EngineResolver(
                    engines,
                    order,
                    strategy=config.strategy,
                    task_id=task_id,
                    on_log=on_log,
                    is_cancelled=is_cancelled,
                    on_rate_limited=lambda: bcut_budget.mark_rate_limited(
                        config.cache_dir or None
                    ),
                )
                # 不把整项本地降级结果写进原 bcut 档案的整段缓存键。
                cache_key = None

        # 无法探知时长或短于阈值 → 整段转录（MUST NOT 误切）
        if duration is None or duration <= threshold:
            measured.update({"segment_count": 1, "worker_count": 1})
            if on_log:
                on_log("info", "音频较短或时长未知，整段转录（不触发 VAD 分段）")
            transcribe_started = time.perf_counter()
            cues = resolver.transcribe(audio_path, on_progress=on_progress)
        else:
            if work_dir is None:
                work_dir = os.path.join(
                    os.path.dirname(os.path.abspath(audio_path)),
                    f".asr_segments_{os.getpid()}",
                )
            if on_log:
                on_log("info", f"音频较长（{duration:.0f}s），触发 VAD 静音切分并行转录")
            split_started = time.perf_counter()
            output_format = config.online_audio_format if online_profile else "wav"
            max_segment = min(threshold, 295.0) if online_profile else threshold
            segments = split_audio_by_silence(
                audio_path,
                duration,
                work_dir,
                max_segment_sec=max_segment,
                target_segment_sec=config.effective_target_segment_seconds(online=online_profile),
                output_format=output_format,
                bitrate_kbps=config.online_audio_bitrate_kbps,
            )
            measured["split_seconds"] = round(time.perf_counter() - split_started, 3)
            measured["segment_count"] = len(segments)
            measured["segment_bytes"] = sum(
                os.path.getsize(seg.path) for seg in segments if os.path.exists(seg.path)
            )
            transcribe_started = time.perf_counter()
            if len(segments) <= 1:
                measured["worker_count"] = 1
                cues = resolver.transcribe(audio_path, on_progress=on_progress)
            else:
                cues = _transcribe_segments_parallel(
                    segments,
                    resolver,
                    config,
                    on_progress,
                    on_log,
                    is_cancelled,
                    online_profile=online_profile,
                    probe_bcut=bool(order and order[0] == ENGINE_BCUT),
                    bcut_cache_dir=config.cache_dir or None,
                    metrics=measured,
                )
        measured["transcribe_seconds"] = round(time.perf_counter() - transcribe_started, 3)
        measured["cue_count"] = len(cues)
        if cache_key and config.cache_enabled:
            asr_cache.put(config.cache_dir, cache_key, cues)
        return cues
    finally:
        if transcribe_started is not None and not measured.get("transcribe_seconds"):
            measured["transcribe_seconds"] = round(time.perf_counter() - transcribe_started, 3)
        if resolver is not None:
            try:
                measured.update(resolver.metrics_snapshot())
            finally:
                resolver.close()
        bcut_engine = engines.get(ENGINE_BCUT)
        if isinstance(bcut_engine, BcutEngine):
            measured.update(bcut_engine.metrics_snapshot())
        measured["total_seconds"] = round(time.perf_counter() - started, 3)


def _transcribe_segments_parallel(
    segments: list[AudioSegment],
    resolver: _EngineResolver,
    config: AsrConfig,
    on_progress: Optional[ProgressCallback],
    on_log: Optional[LogCallback],
    is_cancelled: Optional[CancelCheck],
    *,
    online_profile: bool = False,
    probe_bcut: bool = False,
    bcut_cache_dir: Optional[str] = None,
    metrics: Optional[dict] = None,
) -> list[Cue]:
    """对 VAD 各段并行调用引擎，段内时间戳叠加段起始偏移，拼回单调 SRT。"""
    if is_cancelled and is_cancelled():
        raise CancelledError("ASR 转录被取消")

    total = len(segments)
    workers = max(1, min(config.effective_concurrency(online=online_profile), total))
    if metrics is not None:
        metrics["worker_count"] = workers
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

    def _record_completed(idx: int, applied: list[Cue]) -> None:
        results[idx] = applied
        with progress_lock:
            done_state["done"] += 1
            if on_progress:
                on_progress(
                    int(done_state["done"] / total * 100),
                    f"已转录 {done_state['done']}/{total} 段",
                )
            if on_log:
                on_log(
                    "info",
                    f"分段转录完成：{done_state['done']}/{total}"
                    f"（起始偏移 {segments[idx].start_offset:.0f}s）",
                )

    try:
        first_pending = 0
        if probe_bcut:
            probe_completed = False
            with _BCUT_PROBE_LOCK:
                remaining = bcut_budget.cooldown_remaining(bcut_cache_dir)
                if remaining > 0:
                    resolver.disable_engine(ENGINE_BCUT)
                    if metrics is not None:
                        metrics["bcut_cooldown_skipped"] = True
                else:
                    if metrics is not None:
                        metrics["online_probe_used"] = True
                    idx, applied = _worker(0, segments[0])
                    _record_completed(idx, applied)
                    probe_completed = True
            if not probe_completed:
                idx, applied = _worker(0, segments[0])
                _record_completed(idx, applied)
            first_pending = 1
            if resolver.is_engine_disabled(ENGINE_BCUT):
                workers = max(
                    1,
                    min(config.effective_concurrency(online=False), total),
                )
                if metrics is not None:
                    metrics["worker_count"] = workers

        pending = list(enumerate(segments[first_pending:], start=first_pending))
        with ThreadPoolExecutor(max_workers=min(workers, max(1, len(pending)))) as pool:
            future_to_idx = {pool.submit(_worker, i, seg): i for i, seg in pending}
            for fut in as_completed(future_to_idx):
                idx, applied = fut.result()
                _record_completed(idx, applied)
    finally:
        # 清理临时分段文件（保留原音频）
        for seg in segments:
            try:
                if seg.path and os.path.exists(seg.path):
                    # 仅删除我们抽出的 segment_* 临时文件（非原音频）
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

    metrics: dict = {}
    try:
        cues = transcribe_audio(
            str(audio_abs),
            asr_config,
            on_progress=on_progress,
            on_log=on_log,
            is_cancelled=is_cancelled,
            task_id=task_id,
            work_dir=work_dir,
            metrics=metrics,
        )
    except Exception:
        register_metadata = getattr(ctx, "register_node_metadata", None)
        if callable(register_metadata) and metrics:
            try:
                register_metadata(metrics)
            except Exception:
                _LOGGER.debug("register_node_metadata 失败，已忽略", exc_info=True)
        raise

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

    register_metadata = getattr(ctx, "register_node_metadata", None)
    if callable(register_metadata):
        try:
            register_metadata(metrics)
        except Exception:
            _LOGGER.debug("register_node_metadata 失败，已忽略", exc_info=True)

    if on_log:
        on_log("ok", f"ASR 转写完成，SRT 已写入（{len(cues)} 条字幕，{size_bytes} 字节）")
    # 返回相对 DATA_ROOT 的 POSIX 路径（落库形态）
    try:
        return srt_abs.relative_to(data_root).as_posix()
    except ValueError:
        return srt_out_rel_path
