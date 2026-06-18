"""vid2note 核心类型定义"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from vid2note_core.errors import Vid2NoteError


class TaskId:
    """任务 ID 值对象，防止路径遍历"""

    _TASK_ID_PATTERN = re.compile(r"^task_[a-f0-9]{12}$")

    def __init__(self, value: str) -> None:
        if not self.is_valid(value):
            raise ValueError(f"invalid task_id: {value}")
        self._value = value

    @property
    def value(self) -> str:
        return self._value

    @classmethod
    def generate(cls) -> str:
        """Generate a new valid task_id."""
        import secrets

        return f"task_{secrets.token_hex(6)}"

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return bool(cls._TASK_ID_PATTERN.match(value))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, TaskId):
            return self._value == other._value
        return False

    def __hash__(self) -> int:
        return hash(self._value)

    def __repr__(self) -> str:
        return f"TaskId({self._value!r})"


class NodeName(str, Enum):
    """Pipeline 节点名称"""

    DOWNLOAD = "download"
    EXTRACT_AUDIO = "extract_audio"
    TRANSCRIBE = "transcribe"
    ORGANIZE = "organize"
    MINDMAP = "mindmap"
    CLEANUP = "cleanup"


class NodeStatus(str, Enum):
    """节点执行状态"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskStatus(str, Enum):
    """整体任务状态"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    PARTIAL = "partial"


class RunMode(str, Enum):
    """运行模式"""

    ELECTRON = "electron"
    DOCKER = "docker"
    CLI = "cli"
    DEV = "dev"


@dataclass(frozen=True)
class ArtifactRef:
    """产物引用"""

    node: NodeName
    name: str


@dataclass(frozen=True, slots=True)
class NodeFailure:
    code: str
    message: str
    user_message: str
    retryable: bool
    step: str | None = None

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "user_message": self.user_message,
            "retryable": self.retryable,
            "step": self.step,
        }


@dataclass
class NodeResult:
    """节点执行结果"""

    node: NodeName
    status: NodeStatus
    artifacts: list[ArtifactRef] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: NodeFailure | None = None

    @classmethod
    def success(
        cls,
        node: NodeName,
        artifacts: list[ArtifactRef] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> NodeResult:
        return cls(
            node=node,
            status=NodeStatus.COMPLETED,
            artifacts=artifacts or [],
            metadata=metadata or {},
            error=None,
        )

    @classmethod
    def failure(
        cls,
        node: NodeName,
        error_code: Vid2NoteError | str,
        error_message: str | None = None,
        artifacts: list[ArtifactRef] | None = None,
    ) -> NodeResult:
        if isinstance(error_code, Vid2NoteError):
            failure = NodeFailure(
                code=error_code.code,
                message=str(error_code),
                user_message=error_code.user_message,
                retryable=error_code.retryable,
                step=error_code.step,
            )
        else:
            message = error_message or error_code
            failure = NodeFailure(
                code=error_code,
                message=message,
                user_message=message,
                retryable=False,
                step=node.value,
            )
        return cls(
            node=node,
            status=NodeStatus.FAILED,
            artifacts=artifacts or [],
            error=failure,
        )
