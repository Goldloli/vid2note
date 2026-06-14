"""下载器路由"""
from pathlib import Path
from typing import List
from vid2note_core.downloaders.base import IDownloader, DownloadOpts, DownloadResult
from vid2note_core.errors import DownloadError


class DownloaderRouter:
    def __init__(self, downloaders: List[IDownloader]):
        self.downloaders = downloaders

    def select(self, url_or_path: str) -> IDownloader:
        for dl in self.downloaders:
            if dl.can_handle(url_or_path):
                return dl
        raise DownloadError(f"没有下载器能处理: {url_or_path}", code="DOWNLOAD_NO_HANDLER")

    def download_with_fallback(self, url: str, dest_dir: Path, opts: DownloadOpts) -> DownloadResult:
        primary = self.select(url)
        try:
            return primary.download(url, dest_dir, opts)
        except Exception as e:
            # 尝试其他下载器
            for dl in self.downloaders:
                if dl is primary:
                    continue
                if dl.can_handle(url):
                    try:
                        return dl.download(url, dest_dir, opts)
                    except Exception:
                        continue
            raise
