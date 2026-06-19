from __future__ import annotations

import json
import platform
import shutil
from pathlib import Path


class SandboxPolicy:
    def __init__(self, vault_root: Path, workspace: Path, runtime_home: Path):
        self.vault_root = vault_root.resolve()
        self.workspace = workspace.resolve()
        self.runtime_home = runtime_home.resolve()
        self.runtime_home.mkdir(parents=True, exist_ok=True)
        self.executable = shutil.which("sandbox-exec") if platform.system() == "Darwin" else None

    @property
    def available(self) -> bool:
        return self.executable is not None

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
