import asyncio
import sys
from pathlib import Path

from vid2note_core.agents.subprocess import ManagedProcessRunner

FAKE = Path(__file__).parents[2] / "fake_cli" / "fake_agent.py"


class PassthroughSandbox:
    available = True
    unavailable_reason = None
    runtime_home = None
    proxy_url = "http://localhost:43123"

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


def test_runner_redacts_credentials_from_stdout_stderr_and_urls(tmp_path):
    runner = ManagedProcessRunner(PassthroughSandbox())

    result = asyncio.run(
        runner.run("run_secrets", sys.executable, [str(FAKE), "secrets"], "", tmp_path)
    )

    output = "\n".join([*result.stdout_lines, result.stderr])
    assert "stdout-token" not in output
    assert "url-token" not in output
    assert "stderr-cookie" not in output
    assert "stderr-key" not in output
    assert output.count("[REDACTED]") >= 4


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


def test_runner_explicit_cancel_is_distinct_from_failure(tmp_path):
    async def scenario():
        runner = ManagedProcessRunner(PassthroughSandbox())
        task = asyncio.create_task(
            runner.run("run_4", sys.executable, [str(FAKE), "sleep"], "", tmp_path)
        )
        await asyncio.sleep(0.05)
        await runner.cancel("run_4")
        return await task

    result = asyncio.run(scenario())
    assert result.cancelled
    assert not result.timed_out


def test_runner_passes_only_explicit_auth_and_proxy_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "controlled-key")
    monkeypatch.setenv("UNRELATED_SECRET", "must-not-pass")
    runner = ManagedProcessRunner(PassthroughSandbox(), auth_env={"OPENAI_API_KEY"})

    environment = runner._environment()

    assert environment["OPENAI_API_KEY"] == "controlled-key"
    assert environment["HTTPS_PROXY"] == "http://localhost:43123"
    assert environment["HTTP_PROXY"] == "http://localhost:43123"
    assert "UNRELATED_SECRET" not in environment
