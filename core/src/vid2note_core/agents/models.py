from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.types import JsonValue

AgentEventType = Literal[
    "run.started",
    "thinking.delta",
    "message.delta",
    "tool.started",
    "tool.completed",
    "file.observed",
    "changeset.proposed",
    "approval.required",
    "usage",
    "run.completed",
    "run.failed",
    "run.cancelled",
]

TERMINAL_EVENT_TYPES = frozenset({"run.completed", "run.failed", "run.cancelled"})


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class AgentCapabilities(FrozenModel):
    streaming: bool
    resume: bool
    file_edits: bool
    media_requests: bool
    models: list[str]


class DetectionResult(FrozenModel):
    available: bool
    version: str | None = None
    auth_status: Literal["authenticated", "unauthenticated", "unknown"]
    reason: str | None = None


class AgentRunInput(FrozenModel):
    run_id: str
    session_id: str
    message: str = Field(min_length=1)
    context_paths: list[str]
    model: str | None = None


class AgentEvent(FrozenModel):
    run_id: str
    sequence: int = Field(ge=0)
    type: AgentEventType
    timestamp: datetime
    payload: dict[str, JsonValue]


class RuntimeDescriptor(FrozenModel):
    id: str
    label: str
    executable: str | None
    version_args: list[str]
    auth_args: list[str] | None
    detection_timeout_ms: int = Field(default=5000, gt=0)


class AgentSession(FrozenModel):
    id: str
    runtime_id: str
    model: str | None = None
    context_paths: list[str]
    status: Literal["created", "running", "completed", "failed", "cancelled"]
    created_at: datetime
    updated_at: datetime


class AgentRun(FrozenModel):
    id: str
    session_id: str
    status: Literal["running", "completed", "failed", "cancelled"]
    created_at: datetime
    completed_at: datetime | None = None
