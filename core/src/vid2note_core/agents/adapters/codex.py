from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable
from typing import Protocol

from vid2note_core.agents.adapters.common import normalize_native
from vid2note_core.agents.events import AgentEventEmitter
from vid2note_core.agents.models import (
    AgentCapabilities,
    AgentEvent,
    AgentRunInput,
    DetectionResult,
)
from vid2note_core.agents.parsers.codex_jsonl import CodexJsonlParser
from vid2note_core.agents.subprocess import ManagedProcessRunner
from vid2note_core.agents.workspace import AgentWorkspace, WorkspaceDiff


class WorkspaceFactory(Protocol):
    def __call__(self, input: AgentRunInput) -> AgentWorkspace: ...


class CodexAdapter:
    id = "codex"

    def __init__(
        self,
        runner: ManagedProcessRunner,
        workspace_factory: WorkspaceFactory,
        *,
        executable: str = "codex",
        persist_diff: Callable[[AgentRunInput, AgentWorkspace, list[WorkspaceDiff]], str | None]
        | None = None,
    ):
        self.runner = runner
        self.workspace_factory = workspace_factory
        self.executable = executable
        self.persist_diff = persist_diff
        self.native_sessions: dict[str, str] = {}

    async def detect(self) -> DetectionResult:
        available = self.runner.sandbox.available
        return DetectionResult(
            available=available,
            auth_status="unknown",
            reason=None if available else "sandbox_unavailable",
        )

    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            streaming=True, resume=True, file_edits=True, media_requests=False, models=[]
        )

    async def run(self, input: AgentRunInput) -> AsyncIterator[AgentEvent]:
        emitter = AgentEventEmitter(input.run_id)
        yield emitter.emit("run.started", {"runtime_id": self.id})
        workspace = self.workspace_factory(input)
        args = [
            "exec",
            "--json",
            "--skip-git-repo-check",
            "--sandbox",
            "workspace-write",
            "-c",
            "sandbox_workspace_write.network_access=false",
            "-c",
            'default_permissions=":workspace"',
            "-C",
            str(workspace.root),
        ]
        if input.model is not None:
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", input.model):
                yield emitter.emit("run.failed", {"code": "AGENT_MODEL_INVALID"})
                return
            args.extend(["--model", input.model])
        result = await self.runner.run(
            input.run_id, self.executable, args, input.message, workspace.root
        )
        if result.cancelled:
            yield emitter.emit("run.cancelled", {})
            return
        parser = CodexJsonlParser()
        terminal_native = None
        for line in result.stdout_lines:
            for native in parser.parse_line(line):
                if native.type == "session":
                    self.native_sessions[input.session_id] = str(
                        native.payload["native_session_id"]
                    )
                    continue
                if native.type in {"completed", "failed"}:
                    terminal_native = native
                    continue
                normalized = normalize_native(emitter, native)
                if normalized is None:
                    continue
                yield normalized
        if len(parser.diagnostics) > 20:
            yield emitter.emit("run.failed", {"code": "AGENT_PROTOCOL_ERROR"})
            return
        if terminal_native is not None and terminal_native.type == "completed":
            diffs = workspace.collect_diff()
            if diffs and self.persist_diff is not None:
                changeset_id = self.persist_diff(input, workspace, diffs)
                if changeset_id is not None:
                    yield emitter.emit("changeset.proposed", {"changeset_id": changeset_id})
                    yield emitter.emit("approval.required", {"changeset_id": changeset_id})
            workspace.cleanup()
        if terminal_native is None:
            terminal = emitter.emit(
                "run.failed",
                {
                    "code": "AGENT_PROCESS_FAILED",
                    "returncode": result.returncode,
                    "stderr": result.stderr,
                },
            )
        else:
            normalized_terminal = normalize_native(emitter, terminal_native)
            assert normalized_terminal is not None
            terminal = normalized_terminal
        yield terminal

    async def cancel(self, run_id: str) -> None:
        await self.runner.cancel(run_id)

    async def resume(self, session_id: str, message: str) -> AsyncIterator[AgentEvent]:
        if session_id not in self.native_sessions:
            emitter = AgentEventEmitter(f"run_{session_id[-12:]}")
            yield emitter.emit("run.started", {"runtime_id": self.id})
            yield emitter.emit("run.failed", {"code": "AGENT_RESUME_MISSING"})
            return
        async for event in self.run(
            AgentRunInput(
                run_id=f"run_{session_id[-12:]}",
                session_id=session_id,
                message=message,
                context_paths=[],
            )
        ):
            yield event
