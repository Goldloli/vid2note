"""
In-memory SSE event bus for vid2note.
Supports per-task broadcast channels with asyncio.Queue.
"""

import asyncio
import contextlib
import json
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TaskEvent:
    """SSE event payload"""

    task_id: str
    event_type: (
        str  # task.created, node.started, node.completed, node.failed, task.completed, task.failed
    )
    node_name: str | None = None
    node_status: str | None = None
    progress: int | None = None
    message: str | None = None
    artifact: str | None = None
    timestamp: str | None = None

    def to_sse_payload(self) -> str:
        data = {
            "task_id": self.task_id,
            "event_type": self.event_type,
            "node_name": self.node_name,
            "node_status": self.node_status,
            "progress": self.progress,
            "message": self.message,
            "artifact": self.artifact,
            "timestamp": self.timestamp or datetime.now().isoformat(),
        }
        # Remove None values for compactness
        return f"data: {json.dumps({k: v for k, v in data.items() if v is not None})}\n\n"


class EventBus:
    """In-memory broadcaster: one queue per connected SSE client per task."""

    def __init__(self):
        self._channels: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, task_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._channels.setdefault(task_id, []).append(queue)
        return queue

    def unsubscribe(self, task_id: str, queue: asyncio.Queue) -> None:
        if task_id in self._channels:
            self._channels[task_id] = [q for q in self._channels[task_id] if q is not queue]
            if not self._channels[task_id]:
                del self._channels[task_id]

    def publish(self, event: TaskEvent) -> None:
        queues = self._channels.get(event.task_id, [])
        for q in queues:
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(event)  # 队列满时丢弃事件，避免阻塞


# Global singleton
_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus
