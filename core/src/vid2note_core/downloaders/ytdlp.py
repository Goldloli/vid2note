"""yt-dlp 下载器"""

import subprocess
from pathlib import Path

from vid2note_core.downloaders.base import DownloadOpts, DownloadResult, IDownloader
from vid2note_core.downloaders.binary_manager import BinaryManager
from vid2note_core.errors import DownloadError

_DOWNLOAD_TIMEOUT = 1800  # 30 分钟上限


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
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=_DOWNLOAD_TIMEOUT
            )
        except subprocess.TimeoutExpired as e:
            raise DownloadError(
                f"下载超时（>{_DOWNLOAD_TIMEOUT}s）",
                code="DOWNLOAD_TIMEOUT",
                retryable=True,
                user_message="下载超时，请检查网络或更换视频",
                step="download",
            ) from e
        if result.returncode != 0:
            raise DownloadError(
                f"yt-dlp 失败: {result.stderr}",
                code="DOWNLOAD_FAILED",
                retryable=False,
                user_message="视频下载失败，请检查链接是否有效",
                step="download",
            )
        # 查找最新下载的视频文件（用 mtime 避免取到旧文件）
        files = [f for f in dest_dir.iterdir() if f.is_file()]
        videos = [f for f in files if f.suffix.lower() in {".mp4", ".webm", ".mkv"}]
        if not videos:
            raise DownloadError(
                "yt-dlp 完成但未找到视频文件",
                code="DOWNLOAD_NO_OUTPUT",
                retryable=False,
                step="download",
            )
        video = max(videos, key=lambda f: f.stat().st_mtime)
        return DownloadResult(video_path=video, raw_output=result.stdout)
