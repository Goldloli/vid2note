"""测试 yt-dlp 下载器"""

from pathlib import Path
from unittest.mock import patch, MagicMock
from vid2note_core.downloaders.ytdlp import YtdlpDownloader
from vid2note_core.downloaders.base import DownloadOpts


def test_can_handle_youtube():
    dl = YtdlpDownloader()
    assert dl.can_handle("https://youtube.com/watch?v=abc") is True
    assert dl.can_handle("https://vimeo.com/123") is True
    assert dl.can_handle("https://example.com") is False


def test_download_success(tmp_path):
    dl = YtdlpDownloader()
    # 创建模拟视频文件
    (tmp_path / "test.mp4").write_text("fake")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="done")
        with patch.object(dl, "can_handle", return_value=True):
            result = dl.download("https://youtube.com/x", tmp_path, DownloadOpts())
            assert result.video_path is not None
