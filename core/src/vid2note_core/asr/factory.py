"""ASR 工厂"""

from typing import Any

from vid2note_core.asr.base import IASR
from vid2note_core.asr.cloud.bk_adapter import BkAsrAdapter
from vid2note_core.asr.local.funasr import FunASRAdapter


class ASRFactory:
    _providers: dict[str, Any] = {
        # asrtools-b：基于 bk_asr 的免费云端接口（B站必剪/剪映/快手），
        # 无需 API Key、无需 GPU。config["backend"] 可选 bcut/jianying/kuaishou。
        "asrtools-b": BkAsrAdapter,
        "funasr": FunASRAdapter,
    }

    @classmethod
    def create(cls, provider: str, config: dict[str, Any]) -> IASR:
        provider = provider.lower()
        if provider not in cls._providers:
            raise ValueError(f"不支持的 ASR 提供商: {provider}")
        provider_cls = cls._providers[provider]
        # BkAsrAdapter 接收 backend 参数；FunASRAdapter 接收 model_id 等
        if provider == "asrtools-b":
            return provider_cls(
                backend=config.get("backend", "bcut"),
                **{k: v for k, v in config.items() if k != "backend"},
            )
        return provider_cls(**config)

    @classmethod
    def get_available_providers(cls) -> list:
        return list(cls._providers.keys())

    @classmethod
    def register_provider(cls, name: str, asr_class: type):
        cls._providers[name.lower()] = asr_class
