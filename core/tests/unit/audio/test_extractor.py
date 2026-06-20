"""测试音频提取

ffmpeg 为外部二进制，CI 环境可能未安装。测试用 mock 注入，
不依赖真实 ffmpeg。
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from vid2note_core.audio.extractor import AudioExtractor
from vid2note_core.errors import DownloadError


def test_extract_success(tmp_path):
    # mock ffmpeg 解析（避免依赖真实二进制）+ subprocess
    with (
        patch(
            "vid2note_core.audio.ffmpeg_binary.BinaryManager.resolve",
            return_value=Path("/fake/ffmpeg"),
        ),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        extractor = AudioExtractor()
        # extract 内部会检查输出文件存在性，预先创建
        result = tmp_path / "audio.wav"
        result.write_bytes(b"fake wav")
        out = extractor.extract(Path("/tmp/video.mp4"), tmp_path)
        assert out.name == "audio.wav"
        mock_run.assert_called_once()


def test_extract_failure(tmp_path):
    with (
        patch(
            "vid2note_core.audio.ffmpeg_binary.BinaryManager.resolve",
            return_value=Path("/fake/ffmpeg"),
        ),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        extractor = AudioExtractor()
        with pytest.raises(DownloadError) as exc_info:
            extractor.extract(Path("/tmp/video.mp4"), tmp_path)
        assert exc_info.value.code == "AUDIO_EXTRACT_FAILED"
