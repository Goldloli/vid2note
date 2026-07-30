"""MiniMax OpenAI 兼容适配器。"""
from .openai_compatible import OpenAICompatibleLLM


class MiniMaxLLM(OpenAICompatibleLLM):
    provider_label = "MiniMax"
    default_model = "MiniMax-M2.7"
    default_base_url = "https://api.minimaxi.com/v1"
