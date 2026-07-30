"""Ollama OpenAI 兼容适配器。"""
from .openai_compatible import OpenAICompatibleLLM


class OllamaLLM(OpenAICompatibleLLM):
    provider_label = "Ollama"
    default_model = "qwen3.5"
    default_base_url = "http://host.docker.internal:11434/v1"
    default_api_key = "ollama"
