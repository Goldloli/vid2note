import asyncio

from vid2note_core.agents.models import RuntimeDescriptor
from vid2note_core.agents.registry import CommandResult, RuntimeRegistry


class FakeRunner:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    async def run(self, executable, args, timeout_ms):
        self.calls.append((executable, args, timeout_ms))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_registry_detects_version_and_controlled_auth_without_model_call(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "controlled-key")
    runner = FakeRunner([CommandResult(0, "codex 1.2.3", "")])
    registry = RuntimeRegistry(runner=runner)

    result = asyncio.run(registry.detect("codex", refresh=True))

    assert result.available
    assert result.version == "codex 1.2.3"
    assert result.auth_status == "authenticated"
    assert [args for _, args, _ in runner.calls] == [["--version"]]


def test_registry_does_not_report_user_home_login_as_runtime_auth(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    runner = FakeRunner([CommandResult(0, "codex 1.2.3", "")])

    result = asyncio.run(RuntimeRegistry(runner=runner).detect("codex", refresh=True))

    assert result.available
    assert result.auth_status == "unauthenticated"
    assert len(runner.calls) == 1


def test_registry_reports_missing_and_timeout():
    descriptor = RuntimeDescriptor(
        id="custom",
        label="Custom",
        executable="missing",
        version_args=["--version"],
        auth_args=None,
        detection_timeout_ms=5,
    )
    missing = RuntimeRegistry(runner=FakeRunner([FileNotFoundError()]), descriptors=[descriptor])
    timeout = RuntimeRegistry(runner=FakeRunner([TimeoutError()]), descriptors=[descriptor])

    assert asyncio.run(missing.detect("custom")).reason == "executable_missing"
    assert asyncio.run(timeout.detect("custom")).reason == "detection_timeout"


def test_registry_caches_and_refreshes_detection(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "controlled-key")
    runner = FakeRunner(
        [
            CommandResult(0, "claude 1", ""),
            CommandResult(0, "claude 2", ""),
        ]
    )
    registry = RuntimeRegistry(runner=runner)

    first = asyncio.run(registry.detect("claude"))
    cached = asyncio.run(registry.detect("claude"))
    refreshed = asyncio.run(registry.detect("claude", refresh=True))

    assert cached == first
    assert refreshed.version == "claude 2"
    assert len(runner.calls) == 2


def test_builtin_is_always_available():
    result = asyncio.run(RuntimeRegistry(runner=FakeRunner([])).detect("built-in"))
    assert result.available and result.auth_status == "authenticated"
