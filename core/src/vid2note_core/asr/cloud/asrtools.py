"""AsrTools b 接口适配器"""
import httpx
import time
from pathlib import Path
from typing import Optional
from vid2note_core.asr.base import IASR, ASRResult, ASRSegment
from vid2note_core.errors import ASRToolBChanged, ASRNetworkError


class AsrToolsBLLM(IASR):
    name = "asrtools-b"
    is_cloud = True
    requires_local_gpu = False

    # b 接口 endpoint（从 AsrTools 项目提取）
    BASE_URL = "https://api.example-asr.com/v1"  # Phase 6 实际调研后填入
    CHUNK_SEC = 60

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or self.BASE_URL
        self.client = httpx.AsyncClient(timeout=30.0)

    async def transcribe(self, audio_path: Path, opts: dict) -> ASRResult:
        # 1. 分块（如果音频超长）
        # 2. 上传每块
        # 3. 轮询结果
        # 4. 合并时间戳
        # TODO: Phase 6 实际实现（需要调研 AsrTools 具体接口）
        raise NotImplementedError("Phase 6 实现")

    def is_available(self) -> bool:
        return True  # 云端始终可用（网络允许）
