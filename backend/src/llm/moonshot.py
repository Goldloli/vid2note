"""Moonshot / Kimi OpenAI 兼容适配器。"""
from .openai_compatible import OpenAICompatibleLLM


class MoonshotLLM(OpenAICompatibleLLM):
    provider_label = "Kimi"
    default_model = "kimi-k2.6"
    default_base_url = "https://api.moonshot.cn/v1"
