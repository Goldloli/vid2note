"""下载器接口"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class DownloadResult:
    video_path: Optional[Path] = None
    audio_path: Optional[Path] = None
    metadata: dict = None
    raw_output: str = ""

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class DownloadOpts:
    cookie_path: Optional[Path] = None
    proxy: Optional[str] = None
    quality: str = "best"  # yt-dlp 质量参数


class IDownloader(ABC):
    name: str = ""

    @abstractmethod
    def can_handle(self, url_or_path: str) -> bool:
        """是否能处理该 URL/路径"""
        ...

    @abstractmethod
    def download(self, url: str, dest_dir: Path, opts: DownloadOpts) -> DownloadResult:
        """下载，返回产物路径"""
        ...
