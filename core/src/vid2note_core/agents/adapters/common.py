from __future__ import annotations

from vid2note_core.agents.events import AgentEventEmitter
from vid2note_core.agents.models import AgentEvent
from vid2note_core.agents.parsers.common import NativeEvent

_EVENT_MAP = {
    "thinking": "thinking.delta",
    "message": "message.delta",
    "file": "file.observed",
    "tool.started": "tool.started",
    "tool.completed": "tool.completed",
    "usage": "usage",
    "completed": "run.completed",
    "failed": "run.failed",
}


def normalize_native(emitter: AgentEventEmitter, event: NativeEvent) -> AgentEvent | None:
    if event.type == "session":
        return None
    event_type = _EVENT_MAP.get(event.type)
    if event_type is None:
        return None
    return emitter.emit(event_type, event.payload)  # type: ignore[arg-type]
