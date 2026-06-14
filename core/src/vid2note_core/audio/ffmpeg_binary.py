"""ffmpeg 二进制管理"""
from pathlib import Path
from vid2note_core.downloaders.binary_manager import BinaryManager


def get_ffmpeg() -> Path:
    return BinaryManager("ffmpeg").resolve()
