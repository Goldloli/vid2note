"""豆包 OpenAI 兼容适配器。"""
from .openai_compatible import OpenAICompatibleLLM


class DoubaoLLM(OpenAICompatibleLLM):
    provider_label = "豆包"
    default_model = "doubao-seed-2-0-lite-260215"
    default_base_url = "https://ark.cn-beijing.volces.com/api/v3"
