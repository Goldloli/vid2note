"""LLM provider 元数据的单一权威来源。"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ProviderDefinition:
    id: str
    name: str
    default_model: str
    default_base_url: str
    credential_fields: tuple[str, ...] = ("api_key",)
    is_local: bool = False
    requires_model: bool = False
    requires_base_url: bool = False
    description: str = ""

    def public_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["credential_fields"] = [
            {
                "id": field,
                "label": "API Key" if field == "api_key" else field,
                "secret": True,
                "required": field == "api_key" and not self.is_local,
            }
            for field in self.credential_fields
        ]
        return value


PROVIDER_REGISTRY: dict[str, ProviderDefinition] = {
    "deepseek": ProviderDefinition(
        "deepseek",
        "DeepSeek",
        "deepseek-v4-flash",
        "https://api.deepseek.com/v1",
        description="DeepSeek OpenAI 兼容接口",
    ),
    "qwen": ProviderDefinition(
        "qwen",
        "通义千问",
        "qwen3.7-plus",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="阿里云百炼 OpenAI 兼容接口",
    ),
    "glm": ProviderDefinition(
        "glm",
        "智谱 GLM",
        "glm-5.2",
        "https://open.bigmodel.cn/api/paas/v4/",
        description="智谱开放平台",
    ),
    "moonshot": ProviderDefinition(
        "moonshot",
        "Kimi",
        "kimi-k2.6",
        "https://api.moonshot.cn/v1",
        description="Moonshot AI OpenAI 兼容接口",
    ),
    "baidu": ProviderDefinition(
        "baidu",
        "百度千帆",
        "ernie-5.0",
        "https://qianfan.baidubce.com/v2",
        description="千帆 v2 Bearer API",
    ),
    "doubao": ProviderDefinition(
        "doubao",
        "豆包",
        "doubao-seed-2-0-lite-260215",
        "https://ark.cn-beijing.volces.com/api/v3",
        description="火山方舟 OpenAI 兼容接口",
    ),
    "minimax": ProviderDefinition(
        "minimax",
        "MiniMax",
        "MiniMax-M2.7",
        "https://api.minimaxi.com/v1",
        description="MiniMax OpenAI 兼容接口",
    ),
    "ollama": ProviderDefinition(
        "ollama",
        "Ollama",
        "qwen3.5",
        "http://host.docker.internal:11434/v1",
        credential_fields=(),
        is_local=True,
        description="本地 OpenAI 兼容服务",
    ),
    "custom": ProviderDefinition(
        "custom",
        "自定义兼容服务",
        "",
        "",
        credential_fields=("api_key",),
        requires_model=True,
        requires_base_url=True,
        description="单个自定义 OpenAI Chat Completions 兼容槽位",
    ),
}


def provider_profiles(
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """把用户覆盖与注册表默认值合并，不改写用户模型。"""
    overrides = overrides or {}
    result: dict[str, dict[str, Any]] = {}
    for provider, definition in PROVIDER_REGISTRY.items():
        raw = overrides.get(provider)
        custom = dict(raw) if isinstance(raw, Mapping) else {}
        result[provider] = {
            "display_name": str(custom.get("display_name") or definition.name),
            "model": str(
                custom["model"]
                if "model" in custom
                else definition.default_model
            ).strip(),
            "base_url": str(
                custom["base_url"]
                if "base_url" in custom
                else definition.default_base_url
            ).strip(),
            "timeout": int(custom.get("timeout") or 120),
        }
    return result


def public_provider_registry() -> list[dict[str, Any]]:
    return [definition.public_dict() for definition in PROVIDER_REGISTRY.values()]


__all__ = [
    "PROVIDER_REGISTRY",
    "ProviderDefinition",
    "provider_profiles",
    "public_provider_registry",
]
