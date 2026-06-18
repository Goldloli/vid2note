"""测试 ASR 工厂"""

import pytest
from vid2note_core.asr.factory import ASRFactory


def test_asrtools_b_is_not_distributed():
    with pytest.raises(ValueError, match="不支持的 ASR 提供商"):
        ASRFactory.create("asrtools-b", {})


def test_asrtools_b_is_not_advertised():
    assert "asrtools-b" not in ASRFactory.get_available_providers()


def test_unsupported_provider():
    with pytest.raises(ValueError):
        ASRFactory.create("unknown", {})


def test_available_providers():
    providers = ASRFactory.get_available_providers()
    assert "funasr" in providers
