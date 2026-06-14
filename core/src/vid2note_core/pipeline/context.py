"""任务上下文"""
from dataclasses import dataclass, field
from typing import Any, Optional
from vid2note_core.types import TaskId


@dataclass
class TaskContext:
    task_id: TaskId
    config: dict = field(default_factory=dict)
    artifacts: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def get_artifact(self, node: str, name: str) -> Optional[Any]:
        return self.artifacts.get(f"{node}/{name}")

    def set_artifact(self, node: str, name: str, value: Any) -> None:
        self.artifacts[f"{node}/{name}"] = value
