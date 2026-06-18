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
            "-i",
            str(video_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            "-y",
            str(output),
        ]
        # encoding/errors：ffmpeg stderr 可能含非 UTF-8 字符（中文文件名），
        # 用 errors="replace" 避免 UnicodeDecodeError（仅用于错误信息展示）
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if result.returncode != 0:
            raise DownloadError(
                f"ffmpeg 失败: {result.stderr}",
                code="AUDIO_EXTRACT_FAILED",
                retryable=True,
            )
        return output
