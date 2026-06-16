"""本地文件下载器"""

import shutil
from pathlib import Path

from vid2note_core.downloaders.base import DownloadOpts, DownloadResult, IDownloader


class LocalFileDownloader(IDownloader):
    name = "local_file"

    def can_handle(self, url_or_path: str) -> bool:
        return Path(url_or_path).exists() and Path(url_or_path).is_file()

    def download(self, url: str, dest_dir: Path, opts: DownloadOpts) -> DownloadResult:
        src = Path(url)
        dest = dest_dir / src.name
        shutil.copy2(src, dest)
        return DownloadResult(video_path=dest)
