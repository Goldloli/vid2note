"""Qwen3-ASR 适配器"""

from pathlib import Path

from vid2note_core.asr.base import IASR, ASRResult
from vid2note_core.asr.local.device import detect_device
from vid2note_core.asr.local.model_manager import ModelManager


class Qwen3ASRAdapter(IASR):
    name = "qwen3-asr"
    is_cloud = False
    requires_local_gpu = True

    def __init__(self, model_id: str = "qwen3-asr-base"):
        self.model_id = model_id
        self.manager = ModelManager()
        self.device = detect_device()

    def transcribe(self, audio_path: Path, opts: dict) -> ASRResult:
        self.manager.get_path(self.model_id)  # 校验模型已下载
        # Phase 7 实际实现：加载 Qwen3-ASR 模型、推理、返回 ASRResult
        raise NotImplementedError("Phase 7 实现")

    def is_available(self) -> bool:
        try:
            self.manager.get_path(self.model_id)
            return True
        except Exception:
            return False
