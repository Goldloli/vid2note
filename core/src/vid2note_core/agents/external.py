from __future__ import annotations

import shutil
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from secrets import token_hex

import yaml

from vid2note_core.agents.adapters.claude import ClaudeAdapter
from vid2note_core.agents.adapters.codex import CodexAdapter
from vid2note_core.agents.models import (
    AgentCapabilities,
    AgentEvent,
    AgentRunInput,
    DetectionResult,
)
from vid2note_core.agents.proxy import AllowlistConnectProxy
from vid2note_core.agents.registry import RUNTIME_AUTH_ENV
from vid2note_core.agents.sandbox import SandboxPolicy
from vid2note_core.agents.subprocess import ManagedProcessRunner
from vid2note_core.agents.workspace import AgentWorkspace, WorkspaceDiff
from vid2note_core.vault.layout import VaultLayout
from vid2note_core.vault.repository import VaultRepository, content_hash
from vid2note_core.wiki.models import ChangeOperation, ChangeSet
from vid2note_core.wiki.store import ChangeSetStore

RUNTIME_NETWORK_TARGETS = {
    "codex": {
        ("api.openai.com", 443),
        ("chatgpt.com", 443),
        ("auth.openai.com", 443),
    },
    "claude": {("api.anthropic.com", 443)},
}


class ExternalCliRuntime:
    def __init__(
        self,
        runtime_id: str,
        layout: VaultLayout,
        repository: VaultRepository,
        changesets: ChangeSetStore,
    ):
        if runtime_id not in {"codex", "claude"}:
            raise ValueError("unsupported external runtime")
        self.id = runtime_id
        self.layout = layout
        self.repository = repository
        self.changesets = changesets
        self._active: dict[str, ManagedProcessRunner] = {}

    async def detect(self) -> DetectionResult:
        executable = shutil.which(self.id)
        policy = self._policy(self.layout.private / "agent-runs" / "detection" / "workspace")
        if not policy.available:
            return DetectionResult(
                available=False, auth_status="unknown", reason="sandbox_unavailable"
            )
        if executable is None:
            return DetectionResult(
                available=False, auth_status="unknown", reason="executable_missing"
            )
        return DetectionResult(available=True, auth_status="unknown")

    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            streaming=True, resume=True, file_edits=True, media_requests=False, models=[]
        )

    async def run(self, input: AgentRunInput) -> AsyncIterator[AgentEvent]:
        executable = shutil.which(self.id)
        if executable is None:
            raise RuntimeError("executable_missing")
        workspace = AgentWorkspace.create(
            self.layout, self.repository, input.run_id, input.context_paths
        )
        proxy = AllowlistConnectProxy(RUNTIME_NETWORK_TARGETS[self.id])
        await proxy.start()
        policy = self._policy(
            workspace.root,
            proxy_port=proxy.port,
            executable=executable,
        )
        runner = ManagedProcessRunner(policy, auth_env=set(RUNTIME_AUTH_ENV[self.id]))
        self._active[input.run_id] = runner
        adapter_type = CodexAdapter if self.id == "codex" else ClaudeAdapter
        adapter = adapter_type(
            runner,
            lambda _: workspace,
            executable=str(policy.executable_path),
            persist_diff=self._persist_diff,
        )
        try:
            async for event in adapter.run(input):
                yield event
        finally:
            self._active.pop(input.run_id, None)
            await proxy.close()

    async def cancel(self, run_id: str) -> None:
        runner = self._active.get(run_id)
        if runner is not None:
            await runner.cancel(run_id)

    async def resume(self, session_id: str, message: str) -> AsyncIterator[AgentEvent]:
        raise RuntimeError("AGENT_RESUME_MISSING")
        yield  # pragma: no cover

    def _policy(
        self,
        workspace_root,
        *,
        proxy_port: int | None = None,
        executable: str | None = None,
    ):
        return SandboxPolicy(
            self.layout.root,
            workspace_root,
            workspace_root.parent / "runtime-home",
            proxy_port=proxy_port,
            executable=None if executable is None else Path(executable),
        )

    def _persist_diff(
        self,
        input: AgentRunInput,
        workspace: AgentWorkspace,
        diffs: list[WorkspaceDiff],
    ) -> str | None:
        operations: list[ChangeOperation] = []
        source_ids: set[str] = set()
        for diff in diffs:
            frontmatter = _frontmatter(diff.after)
            page_id = frontmatter.get("id")
            sources = frontmatter.get("sources", [])
            if not isinstance(page_id, str) or not isinstance(sources, list):
                raise ValueError("external Wiki edits require id and sources frontmatter")
            source_ids.update(item for item in sources if isinstance(item, str))
            current_hash = None
            if diff.action != "create":
                assert diff.before is not None
                current_hash = content_hash(diff.before)
            operations.append(
                ChangeOperation(
                    page_id=page_id,
                    path=diff.path,
                    base_hash=current_hash,
                    action=diff.action,
                    before=diff.before,
                    after=diff.after,
                    rationale=f"Proposed by isolated {self.id} runtime",
                    citations=[],
                )
            )
        if not operations or not source_ids:
            raise ValueError("external Wiki edits require existing source evidence")
        changeset = ChangeSet(
            id=f"chg_{token_hex(6)}",
            created_at=datetime.now(UTC),
            source_ids=sorted(source_ids),
            base_revision=input.run_id,
            agent_runtime=self.id,
            summary=f"Changes proposed by {self.id}",
            operations=operations,
            contradictions=[],
        )
        self.changesets.save_pending(changeset)
        return changeset.id


def _frontmatter(content: str) -> dict[str, object]:
    payload, separator, _ = content.removeprefix("---\n").partition("\n---\n")
    if not separator:
        return {}
    parsed = yaml.safe_load(payload)
    return parsed if isinstance(parsed, dict) else {}
