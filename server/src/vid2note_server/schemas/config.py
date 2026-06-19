"""Configuration API contracts."""

from typing import Any, Literal

from pydantic import BaseModel


class UpdateConfigRequest(BaseModel):
    llm_provider: (
        Literal["qwen", "glm", "deepseek", "moonshot", "baidu", "doubao", "minimax", "ollama"]
        | None
    ) = None
    asr_provider: str | None = None
    keep_video: bool | None = None
    keep_audio: bool | None = None
    keep_srt: bool | None = None
    keep_markdown: bool | None = None
    keep_mindmap: bool | None = None
    language: Literal["zh", "en"] | None = None
    mindmap_format: Literal["mermaid", "outline"] | None = None


class VerifyKeyRequest(BaseModel):
    provider: str
    api_key: str


class ConfigResponse(BaseModel):
    model_config = {"extra": "allow"}


class ConfigUpdateResponse(BaseModel):
    message: str
    changed: list[str]


class VerifyKeyResponse(BaseModel):
    valid: bool
    error: str | None = None


class GenericConfigValue(BaseModel):
    value: Any
