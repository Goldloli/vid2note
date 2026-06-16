"""直链下载器"""

from pathlib import Path

import httpx
from vid2note_core.downloaders.base import DownloadOpts, DownloadResult, IDownloader


class DirectDownloader(IDownloader):
    name = "direct"

    def can_handle(self, url_or_path: str) -> bool:
        return url_or_path.startswith("http") and any(
            url_or_path.endswith(ext) for ext in [".mp4", ".webm", ".mkv", ".mov", ".avi"]
        )

    def download(self, url: str, dest_dir: Path, opts: DownloadOpts) -> DownloadResult:
        output = dest_dir / "video.mp4"
        with httpx.stream("GET", url, follow_redirects=True, timeout=300) as response:
            response.raise_for_status()
            with open(output, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=8192):
                    f.write(chunk)
        return DownloadResult(video_path=output)
