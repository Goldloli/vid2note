from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    data_root: Path
    database: Path
    tasks: Path
    uploads: Path
    models: Path
    config: Path
    vault: Path

    @classmethod
    def from_data_root(cls, root: str | Path) -> RuntimePaths:
        data_root = Path(root).expanduser().resolve()
        data_root.mkdir(parents=True, exist_ok=True)
        vault = data_root / "vault"
        return cls(
            data_root=data_root,
            database=vault / ".vid2note" / "state.sqlite3",
            tasks=data_root / "tasks",
            uploads=data_root / "uploads",
            models=data_root / "models",
            config=data_root / "config.yaml",
            vault=vault,
        )
