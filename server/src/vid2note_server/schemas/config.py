"""Configuration API contracts."""

from typing import Any, Literal

from pydantic import BaseModel, Field
from vid2note_core.config.models import (
    AdvancedConfig,
    ASRConfig,
    ProcessingConfig,
    RetentionConfig,
    WorkspaceConfig,
)
from vid2note_core.wiki.policy import AutonomyMode


class UpdateConfigRequest(BaseModel):
    autonomy_mode: AutonomyMode | None = None
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
    vault_path: str | None = None
    default_runtime: Literal["built-in", "codex", "claude"] | None = None
    clip_buffer_ms: int | None = Field(default=None, ge=0, le=30_000)


class StoreApiKeyRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    api_key: str = Field(min_length=1, max_length=8192)


class VerifyKeyRequest(BaseModel):
    provider: str
    api_key: str


class ConfigResponse(BaseModel):
    """Typed, redacted application configuration returned to the renderer."""

    version: str
    autonomy_mode: AutonomyMode
    llm_provider: Literal[
        "qwen", "glm", "deepseek", "moonshot", "baidu", "doubao", "minimax", "ollama"
    ]
    processing: ProcessingConfig
    advanced: AdvancedConfig
    retention: RetentionConfig
    asr: ASRConfig
    workspace: WorkspaceConfig
    run_mode: str


class ConfigUpdateResponse(BaseModel):
    message: str
    changed: list[str]


class VerifyKeyResponse(BaseModel):
    valid: bool
    error: str | None = None


class GenericConfigValue(BaseModel):
    value: Any
