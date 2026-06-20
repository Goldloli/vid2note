from __future__ import annotations

import json
import platform
import shutil
import subprocess
from pathlib import Path


class SandboxPolicy:
    def __init__(
        self,
        vault_root: Path,
        workspace: Path,
        runtime_home: Path,
        *,
        proxy_port: int | None = None,
        executable: Path | None = None,
    ):
        self.vault_root = vault_root.resolve()
        self.workspace = workspace.resolve()
        self.runtime_home = runtime_home.resolve()
        self.proxy_port = proxy_port
        self.proxy_url = f"http://localhost:{proxy_port}" if proxy_port is not None else None
        self.executable_path = executable.resolve() if executable is not None else None
        self.runtime_home.mkdir(parents=True, exist_ok=True)
        self.executable = shutil.which("sandbox-exec") if platform.system() == "Darwin" else None
        self._verified: bool | None = None

    @property
    def available(self) -> bool:
        if self.executable is None:
            return False
        if self._verified is None:
            self._verified = self._verify()
        return self._verified

    @property
    def unavailable_reason(self) -> str | None:
        return None if self.available else "sandbox_unavailable"

    def profile(self) -> str:
        workspace = json.dumps(str(self.workspace))
        runtime_home = json.dumps(str(self.runtime_home))
        rules = [
            "(version 1)",
            "(deny default)",
            '(import "system.sb")',
            "(allow process*)",
            '(allow file-read* (subpath "/opt/homebrew"))',
            '(allow file-read* (subpath "/usr/local"))',
            f"(allow file-read* file-write* (subpath {workspace}))",
            f"(allow file-read* file-write* (subpath {runtime_home}))",
        ]
        if self.proxy_port is not None:
            rules.append(f'(allow network-outbound (remote tcp "localhost:{self.proxy_port}"))')
        if self.executable_path is not None:
            executable = json.dumps(str(self.executable_path))
            rules.append(f"(allow file-read* (literal {executable}))")
            for parent in self.executable_path.parents:
                rules.append(f"(allow file-read-metadata (literal {json.dumps(str(parent))}))")
        return "\n".join(rules)

    def wrap(self, executable: str, args: list[str]) -> tuple[str, list[str]]:
        if self.executable is None:
            raise RuntimeError("sandbox_unavailable")
        return self.executable, ["-p", self.profile(), "--", executable, *args]

    def _verify(self) -> bool:
        assert self.executable is not None
        self.workspace.mkdir(parents=True, exist_ok=True)
        probe = self.workspace / ".sandbox-probe"
        try:
            write = subprocess.run(
                [
                    self.executable,
                    "-p",
                    self.profile(),
                    "--",
                    "/usr/bin/touch",
                    str(probe),
                ],
                capture_output=True,
                timeout=3,
                check=False,
            )
            read = subprocess.run(
                [
                    self.executable,
                    "-p",
                    self.profile(),
                    "--",
                    "/bin/ls",
                    str(self.vault_root),
                ],
                capture_output=True,
                timeout=3,
                check=False,
            )
            return write.returncode == 0 and probe.is_file() and read.returncode != 0
        except (OSError, subprocess.SubprocessError):
            return False
        finally:
            probe.unlink(missing_ok=True)
