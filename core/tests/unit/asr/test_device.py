"""测试 ASR 设备检测"""
from unittest.mock import patch
from vid2note_core.asr.local.device import detect_device


def test_detect_device_returns_valid():
    device = detect_device()
    assert device in ["cuda", "mps", "cpu"]


def test_detect_cpu_fallback():
    with patch("torch.cuda.is_available", return_value=False):
        with patch("torch.backends.mps.is_available", return_value=False):
            assert detect_device() == "cpu"
