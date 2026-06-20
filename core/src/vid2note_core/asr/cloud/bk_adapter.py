"""Legacy bk_asr adapter boundary.

No backend implementation is distributed. The injectable mapping remains only
to verify the old result-conversion boundary while stored tasks are migrated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vid2note_core.asr.base import IASR, ASRResult, ASRSegment
from vid2note_core.errors import ASRError

_BACKENDS: dict[str, type] = {}


class BkAsrAdapter(IASR):
    """Compatibility boundary with no production backend bundled."""

    name = "asrtools-b"
    is_cloud = True
    requires_local_gpu = False

    def __init__(self, backend: str = "bcut", **kwargs: Any):
        backend = (backend or "bcut").lower()
        if backend not in _BACKENDS:
            raise ValueError(f"不支持的 bk_asr 后端: {backend}，可选: {list(_BACKENDS.keys())}")
        self.backend_name = backend
        self.backend_cls = _BACKENDS[backend]
        # use_cache 关闭：pipeline 每次都应走真实识别
        self.use_cache = bool(kwargs.get("use_cache", False))

    def transcribe(self, audio_path: Path, opts: dict) -> ASRResult:
        language = opts.get("language", "zh")
        # bk_asr 通过文件后缀校验格式（SUPPORTED_SOUND_FORMAT），
        # pipeline 提取出来的音频是 audio.wav，后缀合规。
        bk_audio = self._ensure_readable(audio_path)
        try:
            asr = self.backend_cls(str(bk_audio), use_cache=self.use_cache)
            data = asr.run()
        except Exception as e:  # noqa: BLE001 - bk_asr 底层异常兜底
            raise ASRError(
                f"bk_asr ({self.backend_name}) 识别失败: {e}",
                code="ASR_INFER_FAILED",
                retryable=True,
                user_message=f"云端语音识别失败：{e}",
                step="transcribe",
            ) from e

        segments: list[ASRSegment] = []
        texts: list[str] = []
        for seg in data.segments:
            text = (getattr(seg, "text", "") or "").strip()
            if not text:
                continue
            start_ms = int(getattr(seg, "start_time", 0) or 0)
            end_ms = int(getattr(seg, "end_time", start_ms) or 0)
            segments.append(ASRSegment(start_ms=start_ms, end_ms=end_ms, text=text))
            texts.append(text)

        full = "".join(texts) if language == "zh" else " ".join(texts)
        duration_ms = segments[-1].end_ms if segments else 0
        return ASRResult(
            text_full=full,
            segments=segments,
            language=language,
            duration_ms=duration_ms,
        )

    @staticmethod
    def _ensure_readable(audio_path: Path) -> Path:
        """bk_asr BaseASR 要求文件存在且后缀在白名单内，这里做兜底。"""
        p = Path(audio_path)
        if not p.exists():
            raise ASRError(
                f"音频文件不存在: {p}",
                code="ASR_FILE_NOT_FOUND",
                retryable=False,
                step="transcribe",
            )
        suffix = p.suffix.lower().lstrip(".")
        if suffix not in {"flac", "m4a", "mp3", "wav"}:
            # pipeline 产物是 wav，正常不会走到这里；兜底加个 .wav 后缀
            new_path = p.with_suffix(".wav")
            if not new_path.exists():
                p.rename(new_path)
            return new_path
        return p

    def is_available(self) -> bool:
        return self.backend_name in _BACKENDS
