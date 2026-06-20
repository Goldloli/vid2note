"""本地 ASR 模型管理"""

import json
from collections.abc import Callable
from pathlib import Path

from vid2note_core.errors import ASRModelNotFound


class ModelManager:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def list_available(self) -> list[dict]:
        """返回所有支持的模型元数据"""
        return [
            {
                "id": "funasr-paraformer-small",
                "size_mb": 350,
                "languages": ["zh"],
                "gpu_required": False,
            },
            {
                "id": "funasr-sensevoice-small",
                "size_mb": 600,
                "languages": ["zh", "en"],
                "gpu_required": False,
            },
            {
                "id": "funasr-paraformer-large",
                "size_mb": 1200,
                "languages": ["zh"],
                "gpu_required": True,
            },
            {
                "id": "qwen3-asr-base",
                "size_mb": 1800,
                "languages": ["zh", "en"],
                "gpu_required": True,
            },
        ]

    def list_installed(self) -> list[dict]:
        result = []
        for d in self.base_dir.iterdir():
            manifest = d / "manifest.json"
            if manifest.exists():
                result.append(json.loads(manifest.read_text()))
        return result

    def get_path(self, model_id: str) -> Path:
        p = self.base_dir / model_id
        if not p.exists():
            raise ASRModelNotFound(model_id)
        return p

    async def download(self, model_id: str, progress_callback: Callable | None = None) -> None:
        """从 modelscope / huggingface 下载模型"""
        # Phase 7 实际实现
        raise NotImplementedError("Phase 7 实现")

    def delete(self, model_id: str) -> None:
        import shutil

        p = self.base_dir / model_id
        if p.exists():
            shutil.rmtree(p)
