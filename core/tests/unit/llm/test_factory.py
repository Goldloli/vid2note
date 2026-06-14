"""测试 LLM 工厂"""
import pytest
from vid2note_core.llm.factory import LLMFactory
from vid2note_core.llm.mock import MockLLM


def test_create_qwen():
    llm = LLMFactory.create("qwen", {"api_key": "test", "model": "qwen-turbo"})
    assert llm is not None


def test_create_glm():
    llm = LLMFactory.create("glm", {"api_key": "test", "model": "glm-4-flash"})
    assert llm is not None


def test_create_mock():
    llm = LLMFactory.create("mock", {})
    assert isinstance(llm, MockLLM)


def test_unsupported_provider():
    with pytest.raises(ValueError):
        LLMFactory.create("unknown", {})


def test_available_providers():
    providers = LLMFactory.get_available_providers()
    assert "qwen" in providers
    assert "mock" in providers
