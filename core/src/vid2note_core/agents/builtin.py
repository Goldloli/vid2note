from __future__ import annotations

from collections.abc import AsyncIterator

from vid2note_core.agents.events import AgentEventEmitter
from vid2note_core.agents.models import (
    AgentCapabilities,
    AgentEvent,
    AgentRunInput,
    DetectionResult,
)
from vid2note_core.agents.tools import AgentToolbox


class BuiltinRuntime:
    id = "built-in"

    def __init__(self, toolbox: AgentToolbox):
        self.toolbox = toolbox
        self.cancelled: set[str] = set()

    async def detect(self) -> DetectionResult:
        return DetectionResult(
            available=True,
            version="built-in",
            auth_status="authenticated",
        )

    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            streaming=True,
            resume=True,
            file_edits=False,
            media_requests=True,
            models=[],
        )

    async def run(self, input: AgentRunInput) -> AsyncIterator[AgentEvent]:
        emitter = AgentEventEmitter(input.run_id)
        yield emitter.emit("run.started", {"runtime_id": self.id})
        self.toolbox.read_schema()
        self.toolbox.read_index()
        pages: list[str] = []
        wiki_count = 0
        source_count = 0
        for path in input.context_paths:
            if path.startswith("wiki/") and wiki_count < 12:
                pages.append(self.toolbox.read_page(path))
                wiki_count += 1
            elif source_count < 6 and (
                path.startswith("sources/") or path.endswith("/transcript.md")
            ):
                pages.append(self.toolbox.read_source(path))
                source_count += 1
            if len(self.toolbox.calls) >= 20:
                break
        if input.run_id in self.cancelled:
            yield emitter.emit("run.cancelled", {})
            return
        answer = "\n\n".join(pages) or "No matching Wiki evidence was selected."
        yield emitter.emit(
            "message.delta",
            {
                "text": answer,
                "knowledge_layer": "wiki" if wiki_count else "inference",
                "evidence_gap": not bool(pages),
            },
        )
        yield emitter.emit("run.completed", {})

    async def cancel(self, run_id: str) -> None:
        self.cancelled.add(run_id)

    async def resume(self, session_id: str, message: str) -> AsyncIterator[AgentEvent]:
        async for event in self.run(
            AgentRunInput(
                run_id=f"run_{session_id[-12:]}",
                session_id=session_id,
                message=message,
                context_paths=[],
            )
        ):
            yield event
