from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Literal, Protocol

from vid2note_core.agents.models import (
    AgentCapabilities,
    DetectionResult,
    RuntimeDescriptor,
)


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class DetectionRunner(Protocol):
    async def run(self, executable: str, args: list[str], timeout_ms: int) -> CommandResult: ...


class AsyncDetectionRunner:
    async def run(self, executable: str, args: list[str], timeout_ms: int) -> CommandResult:
        process = await asyncio.create_subprocess_exec(
            executable,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout_ms / 1000
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            raise
        return CommandResult(
            process.returncode or 0,
            stdout.decode(errors="replace").strip(),
            stderr.decode(errors="replace").strip(),
        )


DEFAULT_DESCRIPTORS = (
    RuntimeDescriptor(
        id="built-in",
        label="Built-in Runtime",
        executable=None,
        version_args=[],
        auth_args=None,
    ),
    RuntimeDescriptor(
        id="codex",
        label="Codex CLI",
        executable="codex",
        version_args=["--version"],
        auth_args=["login", "status"],
    ),
    RuntimeDescriptor(
        id="claude",
        label="Claude Code",
        executable="claude",
        version_args=["--version"],
        auth_args=["auth", "status"],
    ),
)


class RuntimeRegistry:
    def __init__(
        self,
        *,
        runner: DetectionRunner | None = None,
        descriptors: list[RuntimeDescriptor] | tuple[RuntimeDescriptor, ...] = DEFAULT_DESCRIPTORS,
        cache_ttl_seconds: float = 30,
    ):
        self.runner = runner or AsyncDetectionRunner()
        self.descriptors = {descriptor.id: descriptor for descriptor in descriptors}
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, tuple[float, DetectionResult]] = {}

    async def detect(self, runtime_id: str, *, refresh: bool = False) -> DetectionResult:
        descriptor = self.descriptors[runtime_id]
        cached = self._cache.get(runtime_id)
        now = time.monotonic()
        if not refresh and cached is not None and now - cached[0] < self.cache_ttl_seconds:
            return cached[1]
        if descriptor.executable is None:
            result = DetectionResult(
                available=True, version="built-in", auth_status="authenticated"
            )
        else:
            result = await self._detect_cli(descriptor)
        self._cache[runtime_id] = (now, result)
        return result

    def clear(self) -> None:
        self._cache.clear()

    def capabilities(self, runtime_id: str) -> AgentCapabilities:
        external = runtime_id != "built-in"
        return AgentCapabilities(
            streaming=True,
            resume=True,
            file_edits=external,
            media_requests=not external,
            models=[],
        )

    async def _detect_cli(self, descriptor: RuntimeDescriptor) -> DetectionResult:
        assert descriptor.executable is not None
        try:
            version = await self.runner.run(
                descriptor.executable,
                descriptor.version_args,
                descriptor.detection_timeout_ms,
            )
            if version.returncode != 0:
                return DetectionResult(
                    available=False,
                    auth_status="unknown",
                    reason="version_failed",
                )
            auth_status: Literal["authenticated", "unauthenticated", "unknown"] = "unknown"
            if descriptor.auth_args is not None:
                auth = await self.runner.run(
                    descriptor.executable,
                    descriptor.auth_args,
                    descriptor.detection_timeout_ms,
                )
                auth_status = "authenticated" if auth.returncode == 0 else "unauthenticated"
            return DetectionResult(
                available=True,
                version=version.stdout or version.stderr,
                auth_status=auth_status,
            )
        except FileNotFoundError:
            return DetectionResult(
                available=False,
                auth_status="unknown",
                reason="executable_missing",
            )
        except TimeoutError:
            return DetectionResult(
                available=False,
                auth_status="unknown",
                reason="detection_timeout",
            )
