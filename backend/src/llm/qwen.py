"""通义千问 OpenAI 兼容适配器。"""
from .openai_compatible import OpenAICompatibleLLM


class QwenLLM(OpenAICompatibleLLM):
    provider_label = "Qwen"
    default_model = "qwen3.7-plus"
    default_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
