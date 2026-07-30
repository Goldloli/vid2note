"""DeepSeek OpenAI 兼容适配器。"""
from .openai_compatible import OpenAICompatibleLLM


class DeepSeekLLM(OpenAICompatibleLLM):
    provider_label = "DeepSeek"
    default_model = "deepseek-v4-flash"
    default_base_url = "https://api.deepseek.com/v1"
