"""测试下载器路由"""

from pathlib import Path
from unittest.mock import MagicMock
from vid2note_core.downloaders.router import DownloaderRouter
from vid2note_core.downloaders.base import DownloadResult


def test_youtube_selects_ytdlp():
    ytdlp = MagicMock()
    ytdlp.can_handle = lambda u: "youtube.com" in u
    ytdlp.name = "ytdlp"
    ytdlp.download = MagicMock(return_value=DownloadResult(video_path=Path("/tmp/v.mp4")))

    router = DownloaderRouter([ytdlp])
    result = router.select("https://youtube.com/x")
    assert result.name == "ytdlp"


def test_bilibili_selects_bbdown():
    bbdown = MagicMock()
    bbdown.can_handle = lambda u: "bilibili.com" in u
    bbdown.name = "bbdown"

    ytdlp = MagicMock()
    ytdlp.can_handle = lambda u: False

    router = DownloaderRouter([bbdown, ytdlp])
    result = router.select("https://bilibili.com/x")
    assert result.name == "bbdown"


def test_fallback_on_failure():
    bbdown = MagicMock()
    bbdown.can_handle = lambda u: True
    bbdown.name = "bbdown"
    bbdown.download = MagicMock(side_effect=RuntimeError("fail"))

    ytdlp = MagicMock()
    ytdlp.can_handle = lambda u: True
    ytdlp.name = "ytdlp"
    ytdlp.download = MagicMock(return_value=DownloadResult(video_path=Path("/tmp/v.mp4")))

    router = DownloaderRouter([bbdown, ytdlp])
    result = router.download_with_fallback("https://bilibili.com/x", Path("/tmp"), MagicMock())
    assert result.video_path == Path("/tmp/v.mp4")
    ytdlp.download.assert_called_once()
