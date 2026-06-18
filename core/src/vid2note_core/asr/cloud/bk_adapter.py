"""基于 bk_asr 的云端 ASR 适配器（B 站必剪 / 剪映 / 快手）。

AsrTools 项目（https://github.com/WEIFENG2333/AsrTools）逆向了三个
免费、无需 API Key、无需 GPU 的云端语音识别接口：

  - BcutASR   B 站"必剪"接口，分片上传 + 轮询，最稳定
  - JianYingASR 剪映接口，需要第三方签名服务
  - KuaiShouASR 快手接口，一次 POST 最简单

本模块把 bk_asr 桥接到 vid2note 的 IASR 接口，作为 `asrtools-b`
provider 的真实实现（替换原先的占位 AsrToolsBLLM）。

默认用 BcutASR（最稳定，纯 HTTP 轮询，无第三方签名依赖）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vid2note_core.asr.base import IASR, ASRResult, ASRSegment
from vid2note_core.asr.bk_asr import BcutASR, JianYingASR, KuaiShouASR
from vid2note_core.errors import ASRError

# provider 名 → bk_asr 类
_BACKENDS = {
    "bcut": BcutASR,
    "jianying": JianYingASR,
    "kuaishou": KuaiShouASR,
}


class BkAsrAdapter(IASR):
    """bk_asr 云端 ASR 适配器（无需 API Key、无需 GPU）。

    通过 bk_asr 调用 B 站必剪 / 剪映 / 快手的免费云端识别接口。
    支持 mp3/flac/m4a/wav；若输入是 wav 会被重命名为 .wav 后缀供 bk_asr 校验。
    """

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
        return True
