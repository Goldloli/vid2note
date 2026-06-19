import asyncio
from pathlib import Path

from vid2note_core.agents.adapters.codex import CodexAdapter
from vid2note_core.agents.models import AgentRunInput
from vid2note_core.agents.subprocess import ManagedProcessRunner, ProcessResult

FIXTURE = Path(__file__).parents[2] / "fixtures" / "agents" / "codex" / "success.jsonl"
FAKE_CLI = Path(__file__).parents[2] / "fake_cli" / "fake_codex.py"


class FakeRunner:
    def __init__(self):
        self.call = None

    async def run(self, *args, **kwargs):
        self.call = (args, kwargs)
        return ProcessResult(0, FIXTURE.read_text().splitlines(), "")

    async def cancel(self, run_id):
        return None


class StubWorkspace:
    def __init__(self, root):
        self.root = root
        self.cleaned = False

    def collect_diff(self):
        return ["changed"]

    def cleanup(self):
        self.cleaned = True


async def _events(adapter, value):
    return [event async for event in adapter.run(value)]


def test_codex_adapter_uses_fixed_safe_argv_and_normalized_events(tmp_path):
    runner = FakeRunner()
    workspace = StubWorkspace(tmp_path)
    adapter = CodexAdapter(
        runner,
        lambda _: workspace,
        persist_diff=lambda *_: "chg_0123456789ab",
    )
    value = AgentRunInput(
        run_id="run_0123456789ab",
        session_id="session_0123456789ab",
        message="Question",
        context_paths=[],
    )

    events = asyncio.run(_events(adapter, value))
    args = runner.call[0][2]

    assert args[:6] == [
        "exec",
        "--json",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "-c",
    ]
    assert "danger-full-access" not in args
    assert runner.call[0][3] == "Question"
    assert events[0].type == "run.started"
    assert events[-1].type == "run.completed"
    assert [event.type for event in events].count("changeset.proposed") == 1
    assert workspace.cleaned


def test_codex_adapter_runs_fake_cli_without_network(tmp_path):
    workspace = StubWorkspace(tmp_path)
    workspace.collect_diff = lambda: []
    adapter = CodexAdapter(
        ManagedProcessRunner(PassthroughSandbox()),
        lambda _: workspace,
        executable=str(FAKE_CLI),
    )
    value = AgentRunInput(
        run_id="run_abcdefabcdef",
        session_id="session_abcdefabcdef",
        message="Question",
        context_paths=[],
    )

    events = asyncio.run(_events(adapter, value))

    assert any(event.payload.get("text") == "Compounding rewards patience." for event in events)


class PassthroughSandbox:
    available = True
    unavailable_reason = None

    def wrap(self, executable, args):
        return executable, args
