"""测试 FunASR 适配器"""
from vid2note_core.asr.local.funasr import FunASRAdapter


def test_funasr_not_available_without_model():
    asr = FunASRAdapter()
    assert asr.is_available() is False


def test_funasr_name():
    asr = FunASRAdapter()
    assert asr.name == "funasr"
