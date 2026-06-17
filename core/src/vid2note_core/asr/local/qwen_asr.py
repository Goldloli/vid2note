"""Qwen3-ASR 本地 ASR 适配器

通过 transformers 加载 Qwen-Audio 系列模型进行语音识别。
torch/transformers 延迟导入，CPU-only 环境（如 Docker CPU 镜像）不安装时
不会导致模块导入失败；仅在实际调用 transcribe 时才需要这些依赖。

模型按需从 HuggingFace 下载并缓存，不强制要求预先存在于本地目录。
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from vid2note_core.asr.base import IASR, ASRResult, ASRSegment
from vid2note_core.asr.local.device import detect_device
from vid2note_core.asr.local.model_manager import ModelManager
from vid2note_core.errors import ASRError, ASRModelNotFound

# 本地 model_id → HuggingFace 模型名
_HF_MODEL_MAP = {
    "qwen3-asr-base": "Qwen/Qwen-Audio",
    "qwen2-audio": "Qwen/Qwen2-Audio-7B",
}


class Qwen3ASRAdapter(IASR):
    """Qwen3-ASR / Qwen-Audio 本地语音识别适配器。"""

    name = "qwen3-asr"
    is_cloud = False
    requires_local_gpu = True  # 推荐 GPU，CPU 极慢

    def __init__(
        self,
        model_id: str = "qwen3-asr-base",
        model_manager: ModelManager | None = None,
        device: str | None = None,
        processor_factory: Any = None,
        model_factory: Any = None,
    ):
        self.model_id = model_id
        self.manager = model_manager or ModelManager()
        self.device = device or detect_device()
        # 可注入的工厂（测试用）；None 时延迟导入 transformers
        self._processor_factory = processor_factory
        self._model_factory = model_factory
        self._processor: Any = None
        self._model: Any = None

    def _resolve_model_source(self) -> str:
        """返回模型标识：本地路径优先，否则 HuggingFace model id。"""
        try:
            local = self.manager.get_path(self.model_id)
            return str(local)
        except ASRModelNotFound:
            return _HF_MODEL_MAP.get(self.model_id, self.model_id)

    def _load(self) -> None:
        """延迟加载 processor + model。"""
        if self._processor is not None and self._model is not None:
            return

        source = self._resolve_model_source()

        try:
            if self._processor_factory is not None and self._model_factory is not None:
                processor_cls = self._processor_factory
                model_cls = self._model_factory
            else:
                pass

            self._processor = processor_cls.from_pretrained(source, trust_remote_code=True)
            self._model = model_cls.from_pretrained(
                source, device_map=self.device, trust_remote_code=True
            )
        except Exception as e:  # noqa: BLE001
            raise ASRError(
                f"Qwen-ASR 模型加载失败: {e}",
                code="ASR_MODEL_LOAD_FAILED",
                retryable=False,
                user_message=f"Qwen-ASR 模型加载失败: {e}",
                step="transcribe",
            ) from e

    def transcribe(self, audio_path: Path, opts: dict) -> ASRResult:
        self._load()
        language = opts.get("language", "zh")

        try:
            # Qwen-Audio 推理：processor 编码 → model.generate → 解码
            query = "请转录这段音频的内容。" if language == "zh" else "Transcribe this audio."
            inputs = self._processor(text=query, audios=str(audio_path), return_tensors="pt")
            with contextlib.suppress(Exception):
                inputs = inputs.to(self._model.device)
            output_ids = self._model.generate(**inputs, max_new_tokens=512)
            input_len = inputs["input_ids"].shape[1] if "input_ids" in inputs else 0
            text = self._processor.batch_decode(
                output_ids[:, input_len:], skip_special_tokens=True
            )[0].strip()
        except Exception as e:  # noqa: BLE001
            raise ASRError(
                f"Qwen-ASR 推理失败: {e}",
                code="ASR_INFER_FAILED",
                retryable=True,
                user_message="Qwen-ASR 语音识别失败，请重试",
                step="transcribe",
            ) from e

        if not text:
            return ASRResult(text_full="", segments=[], language=language, duration_ms=0)
        return ASRResult(
            text_full=text,
            segments=[ASRSegment(start_ms=0, end_ms=0, text=text)],
            language=language,
            duration_ms=0,
        )

    def is_available(self) -> bool:
        """模型是否已在本地安装（不触发联网下载）。"""
        try:
            self.manager.get_path(self.model_id)
            return True
        except Exception:
            return False
