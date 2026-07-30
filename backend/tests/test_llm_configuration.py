"""LLM provider 注册表和当前协议契约测试。"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm.baidu import BaiduLLM
from src.llm.custom import CustomLLM
from src.llm.deepseek import DeepSeekLLM
from src.llm.doubao import DoubaoLLM
from src.llm.factory import LLMFactory
from src.llm.glm import GLMLLM
from src.llm.minimax import MiniMaxLLM
from src.llm.moonshot import MoonshotLLM
from src.llm.ollama import OllamaLLM
from src.llm.qwen import QwenLLM
from src.llm.provider_registry import PROVIDER_REGISTRY, provider_profiles


def test_registry_has_nine_slots_and_current_official_defaults():
    assert list(PROVIDER_REGISTRY) == [
        "deepseek",
        "qwen",
        "glm",
        "moonshot",
        "baidu",
        "doubao",
        "minimax",
        "ollama",
        "custom",
    ]
    assert {
        provider: item.default_model for provider, item in PROVIDER_REGISTRY.items()
    } == {
        "deepseek": "deepseek-v4-flash",
        "qwen": "qwen3.7-plus",
        "glm": "glm-5.2",
        "moonshot": "kimi-k2.6",
        "baidu": "ernie-5.0",
        "doubao": "doubao-seed-2-0-lite-260215",
        "minimax": "MiniMax-M2.7",
        "ollama": "qwen3.5",
        "custom": "",
    }
    assert PROVIDER_REGISTRY["ollama"].credential_fields == ()
    assert PROVIDER_REGISTRY["custom"].requires_model is True
    assert PROVIDER_REGISTRY["custom"].requires_base_url is True


def test_profiles_merge_defaults_without_overwriting_user_model():
    profiles = provider_profiles(
        {
            "deepseek": {
                "model": "deepseek-user-choice",
                "base_url": "https://gateway.example.test/v1",
                "timeout": 33,
            }
        }
    )
    assert profiles["deepseek"]["model"] == "deepseek-user-choice"
    assert profiles["deepseek"]["base_url"] == "https://gateway.example.test/v1"
    assert profiles["deepseek"]["timeout"] == 33
    assert profiles["qwen"]["model"] == "qwen3.7-plus"
    assert profiles["custom"]["model"] == ""


@pytest.mark.parametrize(
    ("adapter", "model"),
    [
        (DeepSeekLLM, "deepseek-v4-flash"),
        (QwenLLM, "qwen3.7-plus"),
        (GLMLLM, "glm-5.2"),
        (MoonshotLLM, "kimi-k2.6"),
        (BaiduLLM, "ernie-5.0"),
        (DoubaoLLM, "doubao-seed-2-0-lite-260215"),
        (MiniMaxLLM, "MiniMax-M2.7"),
        (OllamaLLM, "qwen3.5"),
        (CustomLLM, "custom-model"),
    ],
)
def test_openai_compatible_adapters_keep_custom_base_url_and_per_call_timeout(
    monkeypatch, adapter, model
):
    from src.llm import openai_compatible as compatible

    calls: dict[str, object] = {"construct": [], "timeouts": [], "requests": []}

    class FakeCompletions:
        def create(self, **kwargs):
            calls["requests"].append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="pong"))]
            )

    class FakeClient:
        def __init__(self, **kwargs):
            calls["construct"].append(kwargs)
            self.chat = SimpleNamespace(completions=FakeCompletions())

        def with_options(self, **kwargs):
            calls["timeouts"].append(kwargs["timeout"])
            return self

    monkeypatch.setattr(compatible, "OpenAI", FakeClient)
    instance = adapter(
        api_key="sk-test",
        model=model,
        base_url="https://gateway.example.test/openai/v1/",
        timeout=77,
    )

    result = instance.chat(
        [{"role": "user", "content": "ping"}],
        timeout=9,
        max_tokens=3,
    )

    assert result == "pong"
    assert calls["construct"] == [
        {
            "api_key": "sk-test",
            "base_url": "https://gateway.example.test/openai/v1",
            "timeout": 77.0,
        }
    ]
    assert calls["timeouts"] == [9.0]
    assert calls["requests"][0]["model"] == model
    assert calls["requests"][0]["max_tokens"] == 3


def test_baidu_and_minimax_no_longer_require_legacy_secret_fields(monkeypatch):
    from src.llm import openai_compatible as compatible

    class FakeClient:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **_kwargs: SimpleNamespace(
                        choices=[
                            SimpleNamespace(message=SimpleNamespace(content="ok"))
                        ]
                    )
                )
            )

        def with_options(self, **_kwargs):
            return self

    monkeypatch.setattr(compatible, "OpenAI", FakeClient)
    assert BaiduLLM(api_key="one", model="ernie-5.0").chat([]) == "ok"
    assert MiniMaxLLM(api_key="two", model="MiniMax-M2.7").chat([]) == "ok"


def test_custom_adapter_validation_and_factory_registration(monkeypatch):
    from src.llm import openai_compatible as compatible

    monkeypatch.setattr(
        compatible,
        "OpenAI",
        lambda **_kwargs: SimpleNamespace(chat=SimpleNamespace(completions=None)),
    )
    with pytest.raises(ValueError, match="model"):
        CustomLLM(api_key="", model="", base_url="https://example.test/v1")
    with pytest.raises(ValueError, match="base_url"):
        CustomLLM(api_key="", model="custom-model", base_url="")
    custom = LLMFactory.create(
        "custom",
        {
            "api_key": "",
            "model": "custom-model",
            "base_url": "https://example.test/v1",
        },
    )
    assert isinstance(custom, CustomLLM)
