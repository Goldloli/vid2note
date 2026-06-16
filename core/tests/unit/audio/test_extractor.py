"""测试音频提取"""

from unittest.mock import patch, MagicMock
from pathlib import Path
from vid2note_core.audio.extractor import AudioExtractor


def test_extract_success(tmp_path):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        extractor = AudioExtractor()
        result = extractor.extract(Path("/tmp/video.mp4"), tmp_path)
        assert result.name == "audio.wav"
        mock_run.assert_called_once()


def test_extract_failure():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        extractor = AudioExtractor()
        try:
            extractor.extract(Path("/tmp/video.mp4"), Path("/tmp"))
            assert False, "should raise"
        except Exception as e:
            assert "AUDIO_EXTRACT_FAILED" in str(e) or "ffmpeg" in str(e)
