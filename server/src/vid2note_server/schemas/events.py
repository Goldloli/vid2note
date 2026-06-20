"""Server-sent event contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TaskEvent(BaseModel):
    task_id: str
    event_type: Literal[
        "task.created",
        "task.started",
        "task.retrying",
        "task.rerun",
        "task.completed",
        "task.failed",
        "task.interrupted",
        "node.started",
        "node.completed",
        "node.failed",
    ]
    progress: int = Field(ge=0, le=100)
    message: str | None = None
    timestamp: datetime
    node_name: str | None = None
    node_status: str | None = None
    artifact: str | None = None
