from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class ProcessSandbox(Protocol):
    available: bool
    unavailable_reason: str | None

    def wrap(self, executable: str, args: list[str]) -> tuple[str, list[str]]: ...


@dataclass(frozen=True, slots=True)
class ProcessResult:
    returncode: int
    stdout_lines: list[str]
    stderr: str
    timed_out: bool = False
    cancelled: bool = False


class ManagedProcessRunner:
    def __init__(self, sandbox: ProcessSandbox, *, auth_env: set[str] | None = None):
        self.sandbox = sandbox
        self.auth_env = auth_env or set()
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._cancelled: set[str] = set()

    async def run(
        self,
        run_id: str,
        executable: str,
        args: list[str],
        prompt: str,
        cwd: Path,
        *,
        timeout_seconds: float = 300,
    ) -> ProcessResult:
        if not self.sandbox.available:
            raise RuntimeError(self.sandbox.unavailable_reason or "sandbox_unavailable")
        command, wrapped_args = self.sandbox.wrap(executable, args)
        environment = self._environment()
        process = await asyncio.create_subprocess_exec(
            command,
            *wrapped_args,
            cwd=cwd,
            env=environment,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=1024 * 1024 + 1,
        )
        self._processes[run_id] = process
        assert process.stdin is not None
        process.stdin.write(prompt.encode())
        await process.stdin.drain()
        process.stdin.close()
        stdout_task = asyncio.create_task(self._read_stdout(process))
        stderr_task = asyncio.create_task(self._read_stderr(process))
        timed_out = False
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
        except TimeoutError:
            timed_out = True
            await self._terminate(process)
        finally:
            self._processes.pop(run_id, None)
        stdout_lines, stderr = await asyncio.gather(stdout_task, stderr_task)
        cancelled = run_id in self._cancelled
        self._cancelled.discard(run_id)
        return ProcessResult(
            returncode=process.returncode if process.returncode is not None else -1,
            stdout_lines=[_redact(line) for line in stdout_lines],
            stderr=_redact(stderr),
            timed_out=timed_out,
            cancelled=cancelled,
        )

    async def cancel(self, run_id: str) -> None:
        process = self._processes.get(run_id)
        if process is not None:
            self._cancelled.add(run_id)
            await self._terminate(process)

    async def _terminate(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            process.kill()
            await process.wait()

    @staticmethod
    async def _read_stdout(process: asyncio.subprocess.Process) -> list[str]:
        assert process.stdout is not None
        lines: list[str] = []
        while True:
            try:
                line = await process.stdout.readline()
            except ValueError as exc:
                raise RuntimeError("AGENT_PROTOCOL_LINE_TOO_LARGE") from exc
            if not line:
                return lines
            if len(line) > 1024 * 1024:
                raise RuntimeError("AGENT_PROTOCOL_LINE_TOO_LARGE")
            lines.append(line.decode(errors="replace").rstrip("\r\n"))

    @staticmethod
    async def _read_stderr(process: asyncio.subprocess.Process) -> str:
        assert process.stderr is not None
        payload = bytearray()
        while chunk := await process.stderr.read(8192):
            remaining = 65536 - len(payload)
            if remaining > 0:
                payload.extend(chunk[:remaining])
        return payload.decode(errors="replace")

    def _environment(self) -> dict[str, str]:
        allowed = {"PATH", "LANG", "LC_ALL", "LC_CTYPE", *self.auth_env}
        environment = {key: value for key, value in os.environ.items() if key in allowed}
        runtime_home = getattr(self.sandbox, "runtime_home", None)
        if runtime_home is not None:
            environment["HOME"] = str(runtime_home)
        proxy_url = getattr(self.sandbox, "proxy_url", None)
        if proxy_url is not None:
            environment.update(
                HTTP_PROXY=proxy_url,
                HTTPS_PROXY=proxy_url,
                ALL_PROXY=proxy_url,
                NO_PROXY="",
            )
        return environment


_SECRETS = (
    re.compile(r"(?i)(authorization\s*:\s*(?:bearer|basic)\s+)([^\s]+)"),
    re.compile(r"(?i)(cookie\s*:\s*)([^\r\n]+)"),
    re.compile(
        r"(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret)\s*[:=]\s*)([^\s&]+)"
    ),
)


def _redact(value: str) -> str:
    for pattern in _SECRETS:
        value = pattern.sub(r"\1[REDACTED]", value)
    return value
