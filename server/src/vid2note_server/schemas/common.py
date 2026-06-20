"""Shared API contracts."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from pydantic.types import JsonValue


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    user_message: str
    retryable: bool
    component: str
    operation: str
    details: dict[str, JsonValue] | None = None
    cause_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorEnvelope


class MessageResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    active_tasks: int | None = None
    error: str | None = None


class ArtifactItem(BaseModel):
    key: str
    name: str
    content_type: str
    type: str
    size: int


class ArtifactListResponse(BaseModel):
    task_id: str
    artifacts: list[ArtifactItem]


class ModelInfo(BaseModel):
    model_config = ConfigDict(extra="allow")


class ProviderListResponse(BaseModel):
    llm_providers: list[str]
    asr_providers: list[str]


class ModelListResponse(BaseModel):
    models: list[ModelInfo]


class OllamaStatusResponse(BaseModel):
    running: bool
    models: list[str | None]


class LogsResponse(BaseModel):
    logs: list[str]


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    500: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}
