"""测试 ASR 工厂"""

import pytest
from vid2note_core.asr.cloud.bk_adapter import BkAsrAdapter
from vid2note_core.asr.factory import ASRFactory


def test_create_asrtools_b():
    """asrtools-b 现在由 BkAsrAdapter 实现（基于 bk_asr 云端接口）。"""
    asr = ASRFactory.create("asrtools-b", {})
    assert isinstance(asr, BkAsrAdapter)


def test_create_asrtools_b_with_backend_config():
    """config['backend'] 应透传给 BkAsrAdapter。"""
    asr = ASRFactory.create("asrtools-b", {"backend": "kuaishou"})
    assert isinstance(asr, BkAsrAdapter)
    assert asr.backend_name == "kuaishou"


def test_unsupported_provider():
    with pytest.raises(ValueError):
        ASRFactory.create("unknown", {})


def test_available_providers():
    providers = ASRFactory.get_available_providers()
    assert "asrtools-b" in providers
