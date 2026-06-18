"""FunASR 本地 ASR 适配器

通过 funasr.AutoModel 加载模型并推理。模型按需从 ModelScope/HuggingFace
下载并缓存，因此不强制要求模型预先存在于本地目录（get_path 失败时回退
到 ModelScope model id）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vid2note_core.asr.base import IASR, ASRResult, ASRSegment
from vid2note_core.asr.local.device import detect_device
from vid2note_core.asr.local.model_manager import ModelManager
from vid2note_core.errors import ASRError, ASRModelNotFound

# 本地 model_id → ModelScope 上的实际模型名
_MODELSCOPE_MAP = {
    "funasr-paraformer-small": "paraformer-zh",
    "funasr-sensevoice-small": "iic/SenseVoiceSmall",
    "funasr-paraformer-large": "paraformer-zh-streaming",
}


class FunASRAdapter(IASR):
    name = "funasr"
    is_cloud = False
    requires_local_gpu = False  # CPU 也能跑（慢）

    def __init__(
        self,
        model_id: str = "funasr-paraformer-small",
        model_manager: ModelManager | None = None,
        device: str | None = None,
        auto_model_factory: Any = None,
    ):
        self.model_id = model_id
        if model_manager is None:
            raise TypeError("model_manager is required")
        self.manager = model_manager
        self.device = device or detect_device()
        # 允许注入 AutoModel 工厂（测试用）；默认延迟导入 funasr
        self._auto_model_factory = auto_model_factory
        self._model: Any = None  # 懒加载

    def _resolve_model_source(self) -> str:
        """返回传给 AutoModel 的 model 参数：本地路径优先，否则 ModelScope id。"""
        try:
            local = self.manager.get_path(self.model_id)
            return str(local)
        except ASRModelNotFound:
            return _MODELSCOPE_MAP.get(self.model_id, self.model_id)

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        if self._auto_model_factory is not None:
            factory = self._auto_model_factory
        else:
            from funasr import AutoModel

            factory = AutoModel  # 延迟导入

        try:
            self._model = factory(
                model=self._resolve_model_source(),
                device=self.device,
                disable_pbar=True,
            )
        except Exception as e:  # noqa: BLE001 - 模型加载失败统一转为 ASRError
            raise ASRError(
                f"FunASR 模型加载失败: {e}",
                code="ASR_MODEL_LOAD_FAILED",
                retryable=False,
                user_message=f"语音识别模型加载失败: {e}",
                step="transcribe",
            ) from e
        return self._model

    def transcribe(self, audio_path: Path, opts: dict) -> ASRResult:
        model = self._get_model()
        language = opts.get("language", "zh")
        try:
            res = model.generate(
                input=str(audio_path),
                batch_size_s=300,
                language=language,
            )
        except Exception as e:  # noqa: BLE001 - 推理失败统一转为 ASRError
            raise ASRError(
                f"FunASR 推理失败: {e}",
                code="ASR_INFER_FAILED",
                retryable=True,
                user_message="语音识别失败，请重试",
                step="transcribe",
            ) from e

        return self._parse_result(res, language)

    def _parse_result(self, res: list[dict], language: str) -> ASRResult:
        """把 FunASR 的输出（list[dict]，每项含 text 与可选 timestamp）转为 ASRResult。"""
        if not res:
            return ASRResult(text_full="", segments=[], language=language, duration_ms=0)

        segments: list[ASRSegment] = []
        texts: list[str] = []
        for item in res:
            text = (item.get("text") or "").strip()
            if text:
                texts.append(text)
            ts = item.get("timestamp")
            if ts and isinstance(ts, list) and len(ts) >= 2:
                start_ms = int(ts[0][0]) if isinstance(ts[0], (list, tuple)) else int(ts[0])
                end_ms = int(ts[1][0]) if isinstance(ts[1], (list, tuple)) else int(ts[1])
                segments.append(ASRSegment(start_ms=start_ms, end_ms=end_ms, text=text))
            elif text:
                segments.append(ASRSegment(start_ms=0, end_ms=0, text=text))

        # FunASR 的 text 可能含标点（paraformer 自带），保留原样
        full = "".join(texts) if language == "zh" else " ".join(texts)
        duration_ms = segments[-1].end_ms if segments else 0
        return ASRResult(
            text_full=full,
            segments=segments,
            language=language,
            duration_ms=duration_ms,
        )

    def is_available(self) -> bool:
        """模型是否已在本地安装（不触发联网下载）。"""
        try:
            self.manager.get_path(self.model_id)
            return True
        except Exception:
            return False
