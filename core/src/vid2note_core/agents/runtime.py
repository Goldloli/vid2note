from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from vid2note_core.agents.models import (
    AgentCapabilities,
    AgentEvent,
    AgentRunInput,
    DetectionResult,
)


class AgentRuntime(Protocol):
    id: str

    async def detect(self) -> DetectionResult: ...

    def capabilities(self) -> AgentCapabilities: ...

    def run(self, input: AgentRunInput) -> AsyncIterator[AgentEvent]: ...

    async def cancel(self, run_id: str) -> None: ...

    def resume(self, session_id: str, message: str) -> AsyncIterator[AgentEvent]: ...
