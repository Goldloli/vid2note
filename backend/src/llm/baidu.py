"""百度千帆 v2 Bearer / OpenAI 兼容适配器。"""
from .openai_compatible import OpenAICompatibleLLM


class BaiduLLM(OpenAICompatibleLLM):
    provider_label = "百度千帆"
    default_model = "ernie-5.0"
    default_base_url = "https://qianfan.baidubce.com/v2"
