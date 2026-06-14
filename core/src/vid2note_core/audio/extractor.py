"""ffmpeg 音频提取器"""
import subprocess
from pathlib import Path
from vid2note_core.audio.ffmpeg_binary import get_ffmpeg
from vid2note_core.errors import DownloadError


class AudioExtractor:
    def extract(self, video_path: Path, dest_dir: Path, sample_rate: int = 16000) -> Path:
        output = dest_dir / "audio.wav"
        cmd = [
            str(get_ffmpeg()),
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", str(sample_rate),
            "-ac", "1",
            "-y",
            str(output),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise DownloadError(
                f"ffmpeg 失败: {result.stderr}",
                code="AUDIO_EXTRACT_FAILED",
                retryable=True,
            )
        return output
