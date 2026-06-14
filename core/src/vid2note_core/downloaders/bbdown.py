"""BBDown 下载器"""
import subprocess
from pathlib import Path
from vid2note_core.downloaders.base import IDownloader, DownloadOpts, DownloadResult
from vid2note_core.downloaders.binary_manager import BinaryManager


class BBDownDownloader(IDownloader):
    name = "bbdown"

    def can_handle(self, url_or_path: str) -> bool:
        return "bilibili.com" in url_or_path or "b23.tv" in url_or_path

    def download(self, url: str, dest_dir: Path, opts: DownloadOpts) -> DownloadResult:
        binary = BinaryManager("BBDown").resolve()
        cmd = [str(binary), "-o", str(dest_dir), url]
        if opts.cookie_path:
            cmd.extend(["-c", str(opts.cookie_path)])
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"BBDown failed: {result.stderr}")
        files = list(dest_dir.iterdir())
        video = next((f for f in files if f.suffix in {".mp4", ".flv"}), None)
        return DownloadResult(video_path=video, raw_output=result.stdout)
