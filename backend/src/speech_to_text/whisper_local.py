"""speech_to_text.whisper_local —— 本地 whisper.cpp 引擎（CPU + int8）。

设计依据：design D2 / spec speech-to-text / CONTRACT §6.2。

约束（spec「配置本地 whisper.cpp 引擎」）：
- MUST 以 CPU 推理 + int8 量化模型完成转写。
- **MUST NOT 发起任何网络请求**（含模型自动下载）。

实现策略（先做接口 + 调用占位，按 CONTRACT 允许两种落地）：
1. 优先用 ``faster_whisper``（CTranslate2，int8 量化，arm64 CPU 可用）—— **惰性导入**，
   未安装不阻断模块加载与在线引擎运行。
2. 回退到 whisper.cpp 命令行（``whisper-cli`` / ``whisper-cpp``）经 subprocess 调用。
3. 模型路径 MUST 来自配置；路径不存在时直接抛 ``model_missing``（绝不联网下载）。

线程安全：本地 CPU 模型并发收益低且 ``WhisperModel`` 非线程安全，本引擎内置锁，
在 VAD 并行场景下把各段串行化（在线引擎不受影响）。
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
from typing import Optional

from .engine import (
    REASON_MODEL_MISSING,
    REASON_SERVICE_UNAVAILABLE,
    REASON_TIMEOUT,
    REASON_UNSUPPORTED_FORMAT,
    REASON_UNKNOWN,
    AsrEngine,
    AsrError,
    Cue,
    ProgressCallback,
    parse_srt_to_cues,
)

_LOGGER = logging.getLogger("speech_to_text.whisper")

# whisper.cpp CLI 候选名（按优先级）
_WHISPER_CLI_CANDIDATES = ("whisper-cli", "whisper-cpp", "main")


class WhisperCppEngine(AsrEngine):
    """本地 whisper.cpp / faster-whisper 引擎（CPU + int8，不发网络请求）。

    Args:
        model_path: 模型路径（faster-whisper 目录或 whisper.cpp ``.bin``）。MUST 存在。
        binary: 可选，显式指定 whisper.cpp CLI；为空则自动在 ``PATH`` 查找。
        device: ``"cpu"``（默认，符合 spec 无 GPU 约束）。
        compute_type: ``"int8"``（默认，符合 spec 量化要求）。
        language: 语言提示（``"zh"`` / ``"auto"`` 等）。
    """

    name = "whisper_cpp"

    def __init__(
        self,
        model_path: str = "",
        binary: str = "",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "zh",
    ) -> None:
        self.model_path = model_path or ""
        self.binary = binary or ""
        self.device = (device or "cpu").lower()
        self.compute_type = (compute_type or "int8").lower()
        self.language = (language or "auto").lower()
        # 惰性加载的 faster-whisper 模型（进程内复用）
        self._fw_model = None
        self._fw_ready = False
        self._lock = threading.Lock()

    # ---------------- 公共入口 ---------------- #

    def transcribe(self, audio_path: str, on_progress: Optional[ProgressCallback] = None) -> list[Cue]:
        if not os.path.exists(audio_path):
            raise AsrError(f"音频文件不存在：{audio_path}", reason=REASON_UNSUPPORTED_FORMAT, engine=self.name)
        if not self.model_path or not os.path.exists(self.model_path):
            # spec：MUST NOT 联网；模型缺失即视为本地引擎不可用
            raise AsrError(
                f"本地 whisper 模型缺失：{self.model_path or '(未配置)'}",
                reason=REASON_MODEL_MISSING, engine=self.name,
            )
        # 串行化（本地模型非线程安全，且 CPU 并发收益低）
        with self._lock:
            if on_progress:
                on_progress(10, "本地引擎转录中")
            if self._can_use_faster_whisper():
                cues = self._transcribe_faster_whisper(audio_path)
            else:
                cues = self._transcribe_subprocess(audio_path)
            if on_progress:
                on_progress(100, "本地引擎转录完成")
            return cues

    # ---------------- faster-whisper 路径 ---------------- #

    def _can_use_faster_whisper(self) -> bool:
        """是否可用 faster-whisper（仅探测一次）。"""
        if self._fw_ready:
            return self._fw_model is not None
        self._fw_ready = True
        try:
            from faster_whisper import WhisperModel  # 惰性导入
        except Exception as e:  # ImportError / 缺依赖
            _LOGGER.info("faster_whisper 不可用，回退 whisper.cpp CLI：%s", e)
            self._fw_model = None
            return False
        try:
            # 关闭自动下载：model_path 是本地路径；compute_type=int8 走 CPU 量化
            self._fw_model = WhisperModel(
                self.model_path, device=self.device, compute_type=self.compute_type
            )
            _LOGGER.info("已加载 faster_whisper 模型：%s（%s/%s）", self.model_path, self.device, self.compute_type)
            return True
        except Exception as e:
            _LOGGER.warning("faster_whisper 加载模型失败，回退 whisper.cpp CLI：%s", e)
            self._fw_model = None
            return False

    def _transcribe_faster_whisper(self, audio_path: str) -> list[Cue]:
        try:
            segments, _info = self._fw_model.transcribe(
                audio_path,
                language=None if self.language in ("", "auto") else self.language,
                vad_filter=True,
                beam_size=5,
            )
            cues: list[Cue] = []
            for seg in segments:
                text = (seg.text or "").strip()
                if not text:
                    continue
                cues.append(Cue(start=float(seg.start), end=float(seg.end), text=text))
            if not cues:
                _LOGGER.info("whisper 本地转写无语音内容，返回空 Cue 列表（不伪造）")
            return cues
        except Exception as e:
            # 加载态损坏等：清空以便下次重建，并以「引擎不可用」上报
            self._fw_model = None
            self._fw_ready = False
            raise AsrError(
                f"faster_whisper 转写失败：{e}", reason=REASON_SERVICE_UNAVAILABLE, engine=self.name
            ) from e

    # ---------------- whisper.cpp CLI 路径 ---------------- #

    def _resolve_binary(self) -> Optional[str]:
        if self.binary:
            return self.binary if os.path.exists(self.binary) else shutil.which(self.binary)
        for cand in _WHISPER_CLI_CANDIDATES:
            found = shutil.which(cand)
            if found:
                return found
        return None

    def _transcribe_subprocess(self, audio_path: str) -> list[Cue]:
        binary = self._resolve_binary()
        if not binary:
            raise AsrError(
                "未找到 whisper.cpp CLI（whisper-cli/whisper-cpp），且 faster-whisper 不可用",
                reason=REASON_MODEL_MISSING, engine=self.name,
            )
        # 输出 SRT 到 stdout，再解析为 Cue（确定性、复用 engine.parse_srt_to_cues）
        cmd = [
            binary,
            "-m", self.model_path,
            "-f", audio_path,
            "-osrt",       # 输出 SRT
            "-nt",         # 不输出时间戳到终端冗余（部分版本支持，不支持时被忽略）
            "-l", self.language,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        except subprocess.TimeoutExpired as e:
            raise AsrError("whisper.cpp CLI 执行超时", reason=REASON_TIMEOUT, engine=self.name) from e
        except FileNotFoundError as e:
            raise AsrError("whisper.cpp CLI 不可用", reason=REASON_MODEL_MISSING, engine=self.name) from e
        if proc.returncode != 0:
            raise AsrError(
                f"whisper.cpp CLI 非零退出（{proc.returncode}）：{(proc.stderr or '').strip()[:300]}",
                reason=REASON_UNKNOWN, engine=self.name,
            )
        # CLI 的 SRT 通常写到 <audio>.srt；如未生成则解析 stdout
        srt_text = ""
        sidecar = audio_path + ".srt"
        if os.path.exists(sidecar):
            with open(sidecar, "r", encoding="utf-8", errors="replace") as f:
                srt_text = f.read()
        if not srt_text:
            srt_text = proc.stdout or ""
        cues = parse_srt_to_cues(srt_text)
        if not cues:
            _LOGGER.info("whisper.cpp 本地转写无语音内容，返回空 Cue 列表（不伪造）")
        return cues
