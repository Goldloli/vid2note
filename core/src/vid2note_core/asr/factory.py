"""ASR 工厂"""

from typing import Any

from vid2note_core.asr.base import IASR
from vid2note_core.asr.local.funasr import FunASRAdapter


class ASRFactory:
    _providers: dict[str, Any] = {
        "funasr": FunASRAdapter,
    }

    @classmethod
    def create(cls, provider: str, config: dict[str, Any]) -> IASR:
        provider = provider.lower()
        if provider not in cls._providers:
            raise ValueError(f"不支持的 ASR 提供商: {provider}")
        provider_cls = cls._providers[provider]
        return provider_cls(**config)

    @classmethod
    def get_available_providers(cls) -> list:
        return list(cls._providers.keys())

    @classmethod
    def register_provider(cls, name: str, asr_class: type):
        cls._providers[name.lower()] = asr_class
