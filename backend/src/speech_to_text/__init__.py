"""speech_to_text —— ASR 转录能力（design D2/D3 / spec speech-to-text / CONTRACT §6.2）。

公共 API：
- ``Cue``：统一字幕单元（秒）。
- ``AsrEngine``：引擎抽象基类；三实现：
    * ``BcutEngine``（实验性在线，默认首选）
    * ``WhisperCppEngine``（本地 CPU + int8，MUST NOT 发网络请求）
    * ``ExternalAsrEngine``（HTTP endpoint，地址来自配置）
- ``AsrConfig``：引擎与策略配置（``from_settings`` 从运行时设置快照构造）。
- ``transcribe(ctx, audio_rel_path, srt_out_rel_path, asr_config)``：DAG 节点入口（CONTRACT）。
- ``transcribe_to_srt(audio_path, asr_config, ...)``：便捷入口，返回 SRT 文本。
- ``cues_to_srt`` / ``parse_srt_to_cues``：Cue ↔ SRT 文本互转。

字幕一律来自 ASR；本包不存在抓取平台官方字幕（CC）的代码路径（spec speech-to-text）。
"""
from .engine import (
    AsrEngine,
    AsrError,
    CancelledError,
    Cue,
    ProgressCallback,
    cues_to_srt,
    format_srt_timestamp,
    get_audio_duration_seconds,
    parse_srt_to_cues,
    sanitize_cues,
)
from .bcut import BcutEngine
from .whisper_local import WhisperCppEngine
from .external import ExternalAsrEngine
from .vad import AudioSegment, compute_split_points, detect_silence_points, split_audio_by_silence
from .pipeline import (
    AsrConfig,
    build_engines,
    resolve_engine_order,
    transcribe,
    transcribe_audio,
    transcribe_to_srt,
)

__all__ = [
    # 核心类型
    "Cue",
    "AsrEngine",
    "AsrError",
    "CancelledError",
    "ProgressCallback",
    # 引擎实现
    "BcutEngine",
    "WhisperCppEngine",
    "ExternalAsrEngine",
    # 配置与编排
    "AsrConfig",
    "build_engines",
    "resolve_engine_order",
    "transcribe",
    "transcribe_audio",
    "transcribe_to_srt",
    # SRT 工具
    "cues_to_srt",
    "parse_srt_to_cues",
    "format_srt_timestamp",
    "sanitize_cues",
    "get_audio_duration_seconds",
    # VAD
    "AudioSegment",
    "detect_silence_points",
    "compute_split_points",
    "split_audio_by_silence",
]
