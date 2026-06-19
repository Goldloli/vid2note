from __future__ import annotations

from datetime import UTC, datetime

from pydantic.types import JsonValue

from vid2note_core.agents.models import (
    TERMINAL_EVENT_TYPES,
    AgentEvent,
    AgentEventType,
)


class AgentEventEmitter:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.sequence = 0
        self.started = False
        self.terminal = False

    def emit(self, event_type: AgentEventType, payload: dict[str, JsonValue]) -> AgentEvent:
        if self.terminal:
            raise RuntimeError("terminal event already emitted")
        if event_type == "run.started":
            if self.started:
                raise RuntimeError("run.started already emitted")
            self.started = True
        elif not self.started:
            raise RuntimeError("run.started must be emitted first")
        event = AgentEvent(
            run_id=self.run_id,
            sequence=self.sequence,
            type=event_type,
            timestamp=datetime.now(UTC),
            payload=payload,
        )
        self.sequence += 1
        if event_type in TERMINAL_EVENT_TYPES:
            self.terminal = True
        return event
