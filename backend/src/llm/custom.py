"""单个用户自定义 OpenAI Chat Completions 兼容槽位。"""
from .openai_compatible import OpenAICompatibleLLM


class CustomLLM(OpenAICompatibleLLM):
    provider_label = "自定义 LLM"
    default_model = ""
    default_base_url = ""
