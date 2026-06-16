"""下载器接口"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DownloadResult:
    video_path: Path | None = None
    audio_path: Path | None = None
    metadata: dict = field(default_factory=dict)
    raw_output: str = ""

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class DownloadOpts:
    cookie_path: Path | None = None
    proxy: str | None = None
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
