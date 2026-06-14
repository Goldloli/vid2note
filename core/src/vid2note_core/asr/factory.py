"""ASR 工厂"""
from pathlib import Path
from typing import Dict, Any
from vid2note_core.asr.base import IASR
from vid2note_core.asr.cloud.asrtools import AsrToolsBLLM


class ASRFactory:
    _providers: Dict[str, Any] = {
        "asrtools-b": AsrToolsBLLM,
    }

    @classmethod
    def create(cls, provider: str, config: Dict[str, Any]) -> IASR:
        provider = provider.lower()
        if provider not in cls._providers:
            raise ValueError(f"不支持的 ASR 提供商: {provider}")
        return cls._providers[provider](**config)

    @classmethod
    def get_available_providers(cls) -> list:
        return list(cls._providers.keys())

    @classmethod
    def register_provider(cls, name: str, asr_class: type):
        cls._providers[name.lower()] = asr_class
