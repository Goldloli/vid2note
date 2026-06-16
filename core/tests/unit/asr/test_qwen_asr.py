"""测试 Qwen3-ASR 适配器"""

from vid2note_core.asr.local.qwen_asr import Qwen3ASRAdapter


def test_qwen3asr_not_available_without_model():
    asr = Qwen3ASRAdapter()
    assert asr.is_available() is False


def test_qwen3asr_name():
    asr = Qwen3ASRAdapter()
    assert asr.name == "qwen3-asr"
