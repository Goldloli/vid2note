import asyncio
import json
from pathlib import Path

from vid2note_core.agents.adapters.claude import ClaudeAdapter
from vid2note_core.agents.models import AgentRunInput
from vid2note_core.agents.subprocess import ManagedProcessRunner, ProcessResult

FIXTURE = Path(__file__).parents[2] / "fixtures" / "agents" / "claude" / "success.jsonl"
FAKE_CLI = Path(__file__).parents[2] / "fake_cli" / "fake_claude.py"


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

    def collect_diff(self):
        return []

    def cleanup(self):
        return None


async def _events(adapter, value):
    return [event async for event in adapter.run(value)]


def test_claude_adapter_uses_stream_json_envelope_and_safe_argv(tmp_path):
    runner = FakeRunner()
    adapter = ClaudeAdapter(runner, lambda _: StubWorkspace(tmp_path))
    value = AgentRunInput(
        run_id="run_0123456789ab",
        session_id="session_0123456789ab",
        message="Question",
        context_paths=[],
    )

    events = asyncio.run(_events(adapter, value))
    args = runner.call[0][2]
    envelope = json.loads(runner.call[0][3])

    assert args[:7] == [
        "-p",
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
    ]
    assert "--add-dir" not in args
    assert envelope["message"]["content"][0]["text"] == "Question"
    assert events[0].type == "run.started"
    assert events[-1].type == "run.completed"


def test_claude_adapter_runs_fake_cli_without_network(tmp_path):
    adapter = ClaudeAdapter(
        ManagedProcessRunner(PassthroughSandbox()),
        lambda _: StubWorkspace(tmp_path),
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
