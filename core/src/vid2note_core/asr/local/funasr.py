"""FunASR 适配器"""
from pathlib import Path
from vid2note_core.asr.base import IASR, ASRResult
from vid2note_core.asr.local.model_manager import ModelManager
from vid2note_core.asr.local.device import detect_device


class FunASRAdapter(IASR):
    name = "funasr"
    is_cloud = False
    requires_local_gpu = False  # CPU 也能跑（慢）

    def __init__(self, model_id: str = "funasr-paraformer-small"):
        self.model_id = model_id
        self.manager = ModelManager()
        self.device = detect_device()

    def transcribe(self, audio_path: Path, opts: dict) -> ASRResult:
        model_path = self.manager.get_path(self.model_id)
        # Phase 7 实际实现：加载 FunASR 模型、推理、返回 ASRResult
        raise NotImplementedError("Phase 7 实现")

    def is_available(self) -> bool:
        try:
            self.manager.get_path(self.model_id)
            return True
        except Exception:
            return False
