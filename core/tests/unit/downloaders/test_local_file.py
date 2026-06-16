"""测试本地文件下载器"""

from pathlib import Path
from vid2note_core.downloaders.local_file import LocalFileDownloader
from vid2note_core.downloaders.base import DownloadOpts


def test_can_handle_existing_file(tmp_path):
    dl = LocalFileDownloader()
    f = tmp_path / "video.mp4"
    f.write_text("fake")
    assert dl.can_handle(str(f)) is True
    assert dl.can_handle("/nonexistent") is False


def test_download_copies_file(tmp_path):
    dl = LocalFileDownloader()
    src = tmp_path / "source.mp4"
    src.write_text("fake video")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    result = dl.download(str(src), dest_dir, DownloadOpts())
    assert result.video_path.exists()
    assert result.video_path.name == "source.mp4"
