"""you-get 下载器"""
import subprocess
from pathlib import Path
from vid2note_core.downloaders.base import IDownloader, DownloadOpts, DownloadResult
from vid2note_core.downloaders.binary_manager import BinaryManager


class YouGetDownloader(IDownloader):
    name = "youget"

    def can_handle(self, url_or_path: str) -> bool:
        return any(
            domain in url_or_path
            for domain in ["iqiyi.com", "youku.com", "mgtv.com"]
        )

    def download(self, url: str, dest_dir: Path, opts: DownloadOpts) -> DownloadResult:
        binary = BinaryManager("you-get").resolve()
        cmd = [str(binary), "-o", str(dest_dir), url]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"you-get failed: {result.stderr}")
        files = list(dest_dir.iterdir())
        video = next((f for f in files if f.suffix in {".mp4", ".flv"}), None)
        return DownloadResult(video_path=video, raw_output=result.stdout)
