import asyncio
from pathlib import Path

from vid2note_core.agents.adapters.codex import CodexAdapter
from vid2note_core.agents.models import AgentRunInput
from vid2note_core.agents.subprocess import ProcessResult

FIXTURE = Path(__file__).parents[2] / "fixtures" / "agents" / "codex" / "success.jsonl"


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
