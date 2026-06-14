"""ASR 接口"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class ASRSegment:
    start_ms: int
    end_ms: int
    text: str
    speaker: Optional[str] = None


@dataclass
class ASRResult:
    text_full: str
    segments: List[ASRSegment] = field(default_factory=list)
    language: str = "zh"
    duration_ms: int = 0


class IASR(ABC):
    name: str = ""
    is_cloud: bool = False
    requires_local_gpu: bool = False

    @abstractmethod
    def transcribe(self, audio_path: Path, opts: dict) -> ASRResult:
        ...

    def is_available(self) -> bool:
        return True
