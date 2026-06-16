"""yt-dlp 下载器"""

import subprocess
from pathlib import Path

from vid2note_core.downloaders.base import DownloadOpts, DownloadResult, IDownloader
from vid2note_core.downloaders.binary_manager import BinaryManager


class YtdlpDownloader(IDownloader):
    name = "ytdlp"

    def can_handle(self, url_or_path: str) -> bool:
        return any(
            domain in url_or_path
            for domain in ["youtube.com", "youtu.be", "bilibili.com", "vimeo.com"]
        )

    def download(self, url: str, dest_dir: Path, opts: DownloadOpts) -> DownloadResult:
        binary = BinaryManager("yt-dlp").resolve()
        cmd = [
            str(binary),
            "-f",
            opts.quality,
            "-o",
            str(dest_dir / "%(title)s.%(ext)s"),
            "--no-playlist",
            url,
        ]
        if opts.proxy:
            cmd.extend(["--proxy", opts.proxy])
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"yt-dlp failed: {result.stderr}")
        # 查找下载的文件
        files = list(dest_dir.iterdir())
        video = next((f for f in files if f.suffix in {".mp4", ".webm", ".mkv"}), None)
        return DownloadResult(video_path=video, raw_output=result.stdout)
