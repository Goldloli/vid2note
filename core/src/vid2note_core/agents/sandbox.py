from __future__ import annotations

import json
import platform
import shutil
import subprocess
from pathlib import Path


class SandboxPolicy:
    def __init__(self, vault_root: Path, workspace: Path, runtime_home: Path):
        self.vault_root = vault_root.resolve()
        self.workspace = workspace.resolve()
        self.runtime_home = runtime_home.resolve()
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
        vault = json.dumps(str(self.vault_root))
        workspace = json.dumps(str(self.workspace))
        runtime_home = json.dumps(str(self.runtime_home))
        user_home = json.dumps(str(Path.home().resolve()))
        return "\n".join(
            [
                "(version 1)",
                "(allow default)",
                f"(deny file-read* file-write* (subpath {user_home}))",
                f"(deny file-read* file-write* (subpath {vault}))",
                f"(allow file-read* file-write* (subpath {workspace}))",
                f"(allow file-read* file-write* (subpath {runtime_home}))",
            ]
        )

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
