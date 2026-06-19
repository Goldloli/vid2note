import asyncio
import sys
from pathlib import Path

from vid2note_core.agents.subprocess import ManagedProcessRunner

FAKE = Path(__file__).parents[2] / "fake_cli" / "fake_agent.py"


class PassthroughSandbox:
    available = True
    unavailable_reason = None

    def wrap(self, executable, args):
        return executable, args


def test_runner_passes_long_prompt_over_stdin(tmp_path):
    runner = ManagedProcessRunner(PassthroughSandbox())
    prompt = "p" * 100_000

    result = asyncio.run(runner.run("run_1", sys.executable, [str(FAKE), "echo"], prompt, tmp_path))

    assert result.returncode == 0
    assert prompt in result.stdout_lines[0]


def test_runner_limits_and_redacts_stderr(tmp_path):
    runner = ManagedProcessRunner(PassthroughSandbox())
    result = asyncio.run(runner.run("run_2", sys.executable, [str(FAKE), "crash"], "", tmp_path))

    assert result.returncode == 7
    assert len(result.stderr.encode()) <= 65536
    assert "super-secret" not in result.stderr


def test_runner_timeout_terminates_process(tmp_path):
    runner = ManagedProcessRunner(PassthroughSandbox())

    result = asyncio.run(
        runner.run(
            "run_3",
            sys.executable,
            [str(FAKE), "sleep"],
            "",
            tmp_path,
            timeout_seconds=0.05,
        )
    )

    assert result.timed_out
    assert result.returncode != 0
