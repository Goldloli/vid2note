"""speech_to_text.engine —— ASR 引擎抽象接口与共享工具。

设计依据：design D2 / spec speech-to-text / CONTRACT §6.2。

本模块定义：
- ``Cue``：统一字幕单元（start/end 为秒，text 为字幕文本）。
- ``AsrEngine``：所有 ASR 引擎的抽象基类，``transcribe(audio_path, on_progress=None) -> list[Cue]``。
- ``AsrError``：ASR 相关错误的统一异常，携带 ``engine`` / ``reason`` / ``status_code``，
  供 pipeline 的「在线优先失败转本地」降级逻辑判断失败类型并写结构化日志。
- ``CancelledError``：节点被取消时抛出（DAG 注入 ``CancelToken``，见 CONTRACT §5.2.4）。
- 共享工具：``cues_to_srt`` / ``format_srt_timestamp`` / ``parse_srt_to_cues`` /
  ``get_audio_duration_seconds`` / ``sanitize_cues``。

约定：Cue 的时间戳单位统一为「秒（float）」；写 SRT 时由 ``format_srt_timestamp``
统一格式化为 ``HH:MM:SS,mmm``。字幕内容 MUST 完全来自 ASR 转录（spec speech-to-text
「字幕来源一律 ASR」），本模块不得引入任何抓取平台官方字幕（CC）的代码路径。
"""
from __future__ import annotations

import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Optional

# 进度回调签名：(percent: int 0-100, message: str | None) -> None
ProgressCallback = Callable[[int, Optional[str]], None]

# 失败原因枚举（用于降级日志的「原因」字段，保留英文规范用语）
REASON_SERVICE_UNAVAILABLE = "service_unavailable"
REASON_TIMEOUT = "timeout"
REASON_RATE_LIMITED = "rate_limited"          # HTTP 429
REASON_AUTH_FAILED = "auth_failed"
REASON_NETWORK = "network"
REASON_MODEL_MISSING = "model_missing"         # 本地模型文件缺失
REASON_INVALID_RESPONSE = "invalid_response"
REASON_UNSUPPORTED_FORMAT = "unsupported_format"
REASON_UNKNOWN = "unknown"


class CancelledError(Exception):
    """ASR 转录被取消（DAG CancelToken 触发）。

    抛出后由 DAG 节点捕获：丢弃本节点半成品、保留已 completed 产物。
    """


class AsrError(Exception):
    """ASR 引擎统一错误。

    Attributes:
        reason: 失败类型（``REASON_*`` 常量），供降级日志记录「触发降级的原因」。
        engine: 失败的引擎名（``AsrEngine.name``）。
        status_code: HTTP 状态码（在线引擎适用，如 429）。
    """

    def __init__(
        self,
        message: str,
        *,
        reason: str = REASON_UNKNOWN,
        engine: str = "",
        status_code: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.engine = engine
        self.status_code = status_code

    def __str__(self) -> str:  # 中文可读：保留主消息 + 追加上下文
        msg = super().__str__()
        extras: list[str] = []
        if self.engine:
            extras.append(f"引擎={self.engine}")
        if self.reason and self.reason != REASON_UNKNOWN:
            extras.append(f"原因={self.reason}")
        if self.status_code is not None:
            extras.append(f"状态码={self.status_code}")
        if not extras:
            return msg
        return f"{msg}（{'，'.join(extras)}）"


@dataclass
class Cue:
    """统一字幕单元。

    Attributes:
        start: 起始时间戳（秒）。
        end:   结束时间戳（秒）。
        text:  字幕文本（MUST 来自 ASR 转录，不得编造）。
    """

    start: float
    end: float
    text: str


class AsrEngine(ABC):
    """ASR 引擎抽象基类。

    子类 MUST 设置类属性 ``name``（引擎标识，对应配置 ``asr.engine`` 取值），
    并实现 ``transcribe``。实现 MUST NOT 抓取官方字幕，MUST 仅基于音频做 ASR。
    """

    name: str = "abstract"

    @abstractmethod
    def transcribe(
        self,
        audio_path: str,
        on_progress: Optional[ProgressCallback] = None,
    ) -> list[Cue]:
        """转写音频文件为 Cue 列表。

        Args:
            audio_path: 本地音频文件绝对路径。
            on_progress: 可选进度回调（percent 0-100, message）。

        Returns:
            按 start 升序的 ``Cue`` 列表（空列表表示无语音内容，不伪造）。

        Raises:
            AsrError: 引擎不可用 / 超时 / 限流 / 鉴权失败 / 响应非法等。
        """
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# 时间戳与 SRT 格式化
# --------------------------------------------------------------------------- #

def format_srt_timestamp(seconds: float) -> str:
    """秒（float）→ SRT 时间戳 ``HH:MM:SS,mmm``。

    负值钳为 0；毫秒四舍五入。
    """
    if seconds is None or seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    ms = total_ms % 1000
    total_seconds = total_ms // 1000
    s = total_seconds % 60
    total_minutes = total_seconds // 60
    m = total_minutes % 60
    h = total_minutes // 60
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(ms):03d}"


def cues_to_srt(cues: list[Cue]) -> str:
    """Cue 列表 → 标准 SRT 文本。

    输出格式：``序号\\nHH:MM:SS,mmm --> HH:MM:SS,mmm\\n文本\\n\\n``。
    写入前先经 ``sanitize_cues`` 保证时间戳单调递增、无重叠（spec speech-to-text
    「SRT 时间戳单调递增」/「拼合后 SRT 连续单调」）。空列表返回空串（spec：
    纯静音段可如实省略，MUST NOT 伪造字幕条目）。
    """
    cues = sanitize_cues(cues)
    blocks: list[str] = []
    for idx, cue in enumerate(cues, start=1):
        ts = f"{format_srt_timestamp(cue.start)} --> {format_srt_timestamp(cue.end)}"
        text = cue.text.strip()
        blocks.append(f"{idx}\n{ts}\n{text}\n")
    return "\n".join(blocks)


def sanitize_cues(cues: list[Cue]) -> list[Cue]:
    """规整 Cue 列表，保证 SRT 时间戳单调、无重叠、无空条目。

    规则（spec speech-to-text）：
    1. 丢弃 ``text`` 为空白的条目（不伪造字幕）。
    2. 丢弃 ``end <= start`` 的条目。
    3. 按 ``start`` 升序排序。
    4. 消除跨条目重叠：若本条 ``start < 上一条 end``，则把本条 ``start`` 抬到上一条
       ``end``；抬升后若 ``start >= end`` 则丢弃本条。
    """
    cleaned: list[Cue] = []
    for c in cues:
        if c is None:
            continue
        if c.text is None or not str(c.text).strip():
            continue
        if c.end <= c.start:
            continue
        cleaned.append(Cue(start=float(c.start), end=float(c.end), text=str(c.text).strip()))
    cleaned.sort(key=lambda x: x.start)

    result: list[Cue] = []
    for cue in cleaned:
        if result:
            prev_end = result[-1].end
            if cue.start < prev_end:
                # 消除重叠：起点抬到上一条结束
                cue.start = prev_end
                if cue.start >= cue.end:
                    continue  # 抬升后失效，丢弃
        result.append(cue)
    return result


# --------------------------------------------------------------------------- #
# SRT 文本解析（供 ExternalAsrEngine 解析 endpoint 返回的 SRT 串，以及单测复用）
# --------------------------------------------------------------------------- #

_SRT_TS_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})"
)


def _ts_groups_to_seconds(parts: list[str]) -> float:
    h, m, s, ms = (int(x) for x in parts)
    # 毫秒字段位数不一，归一到三位
    if len(str(parts[3])) == 1:
        ms *= 100
    elif len(str(parts[3])) == 2:
        ms *= 10
    return h * 3600 + m * 60 + s + ms / 1000.0


def parse_srt_to_cues(text: str) -> list[Cue]:
    """标准 SRT 文本 → ``Cue`` 列表（宽松解析，容忍 ``.`` / ``,`` 毫秒分隔）。"""
    if not text:
        return []
    cues: list[Cue] = []
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    for block in re.split(r"\n\s*\n", normalized.strip()):
        lines = [ln for ln in block.split("\n") if ln.strip()]
        if len(lines) < 2:
            continue
        # 找到时间戳行（容许首行是序号、或首行即时间戳）
        ts_line_idx = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if ts_line_idx is None:
            continue
        m = _SRT_TS_RE.search(lines[ts_line_idx])
        if not m:
            continue
        start = _ts_groups_to_seconds(list(m.group(1, 2, 3, 4)))
        end = _ts_groups_to_seconds(list(m.group(5, 6, 7, 8)))
        body = "\n".join(lines[ts_line_idx + 1 :]).strip()
        # 剥内联 HTML 标签（<i>...</i> 等）
        body = re.sub(r"<[^>]+>", "", body)
        if body:
            cues.append(Cue(start=start, end=end, text=body))
    return sanitize_cues(cues)


# --------------------------------------------------------------------------- #
# 音频时长探测（供 VAD 决策是否分段）
# --------------------------------------------------------------------------- #

def get_audio_duration_seconds(audio_path: str) -> Optional[float]:
    """用 ffprobe 探测音频时长（秒）；不可用时返回 ``None``。

    返回 ``None`` 时调用方应保守地「不分段」，避免误切。
    """
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    raw = (proc.stdout or "").strip()
    if not raw or raw.upper() == "N/A":
        return None
    try:
        val = float(raw)
    except ValueError:
        return None
    if val <= 0:
        return None
    return val
