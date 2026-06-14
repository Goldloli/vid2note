"""测试 ASR 工厂"""
import pytest
from vid2note_core.asr.factory import ASRFactory
from vid2note_core.asr.cloud.asrtools import AsrToolsBLLM


def test_create_asrtools():
    asr = ASRFactory.create("asrtools-b", {})
    assert isinstance(asr, AsrToolsBLLM)


def test_unsupported_provider():
    with pytest.raises(ValueError):
        ASRFactory.create("unknown", {})


def test_available_providers():
    providers = ASRFactory.get_available_providers()
    assert "asrtools-b" in providers
