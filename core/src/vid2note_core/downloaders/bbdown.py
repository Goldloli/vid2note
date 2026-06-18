"""BBDown 下载器（Bilibili）"""

import subprocess
from pathlib import Path

from vid2note_core.downloaders.base import DownloadOpts, DownloadResult, IDownloader
from vid2note_core.downloaders.binary_manager import BinaryManager
from vid2note_core.errors import DownloadError

# 30 分钟上限：大视频足够，挂死时能及时释放 worker slot
_DOWNLOAD_TIMEOUT = 1800


class BBDownDownloader(IDownloader):
    name = "bbdown"

    def can_handle(self, url_or_path: str) -> bool:
        return "bilibili.com" in url_or_path or "b23.tv" in url_or_path

    def download(self, url: str, dest_dir: Path, opts: DownloadOpts) -> DownloadResult:
        binary = BinaryManager("BBDown").resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)
        # BBDown 用法：BBDown <url> --work-dir <dir>
        # 不传 -p 时默认只下载 URL 指向的分集（合集不会全下）
        cmd = [str(binary), url, "--work-dir", str(dest_dir)]
        if opts.cookie_path:
            cmd.extend(["-c", str(opts.cookie_path)])
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=_DOWNLOAD_TIMEOUT)
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
                f"BBDown 失败: {result.stderr or result.stdout}",
                code="DOWNLOAD_FAILED",
                retryable=False,
                user_message="视频下载失败，请检查链接是否有效",
                step="download",
            )
        # BBDown 可能把视频放在 work-dir 顶层，也可能放在以合集标题命名的子目录里。
        # 用 rglob 递归查找最新生成的视频文件。
        videos = [
            p
            for p in dest_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in {".mp4", ".flv", ".mkv"}
        ]
        if not videos:
            all_files = [p.name for p in dest_dir.rglob("*") if p.is_file()]
            raise DownloadError(
                f"BBDown 完成但未找到视频文件，目录内容: {all_files}",
                code="DOWNLOAD_NO_OUTPUT",
                retryable=False,
                step="download",
            )
        video = max(videos, key=lambda f: f.stat().st_mtime)
        return DownloadResult(video_path=video, raw_output=result.stdout)
