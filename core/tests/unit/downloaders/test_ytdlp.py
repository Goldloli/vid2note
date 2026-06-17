"""测试 yt-dlp 下载器

yt-dlp 为外部二进制，CI 环境可能未安装。测试用 mock 注入，
不依赖真实 yt-dlp。
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from vid2note_core.downloaders.base import DownloadOpts
from vid2note_core.downloaders.ytdlp import YtdlpDownloader


def test_can_handle_youtube():
    dl = YtdlpDownloader()
    assert dl.can_handle("https://youtube.com/watch?v=abc") is True
    assert dl.can_handle("https://vimeo.com/123") is True
    assert dl.can_handle("https://example.com") is False


def test_download_success(tmp_path):
    dl = YtdlpDownloader()
    # 创建模拟视频文件（download 内部会检查产物存在性）
    (tmp_path / "test.mp4").write_text("fake")
    with (
        patch(
            "vid2note_core.downloaders.binary_manager.BinaryManager.resolve",
            return_value=Path("/fake/yt-dlp"),
        ),
        patch("subprocess.run") as mock_run,
        patch.object(dl, "can_handle", return_value=True),
    ):
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="done")
        result = dl.download("https://youtube.com/x", tmp_path, DownloadOpts())
        assert result.video_path is not None
