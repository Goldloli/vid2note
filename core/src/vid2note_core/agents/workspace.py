from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from vid2note_core.vault.layout import VaultLayout
from vid2note_core.vault.repository import VaultRepository

_RUN_ID = re.compile(r"^run_[a-zA-Z0-9_-]{12,64}$")


class AgentWorkspaceViolation(ValueError):  # noqa: N818 - domain violation name
    pass


@dataclass(frozen=True, slots=True)
class WorkspaceDiff:
    action: Literal["create", "update", "rename"]
    path: str
    before: str | None
    after: str
    old_path: str | None = None


class AgentWorkspace:
    def __init__(self, root: Path, layout: VaultLayout, baseline: dict[str, str]):
        self.root = root
        self.layout = layout
        self.baseline = baseline

    @classmethod
    def create(
        cls,
        layout: VaultLayout,
        repository: VaultRepository,
        run_id: str,
        context_paths: list[str],
    ) -> AgentWorkspace:
        if not _RUN_ID.fullmatch(run_id):
            raise ValueError("invalid run id")
        root = layout.private / "agent-runs" / run_id / "workspace"
        if root.exists():
            raise FileExistsError(root)
        root.mkdir(parents=True)
        selected = ["AGENTS.md", "index.md", *context_paths]
        baseline: dict[str, str] = {}
        for relative in selected:
            if relative not in {"AGENTS.md", "index.md"} and not (
                relative.startswith("wiki/")
                or relative.startswith("sources/")
                or (relative.startswith("raw/") and relative.endswith("/transcript.md"))
            ):
                raise AgentWorkspaceViolation(f"out-of-scope context: {relative}")
            page = repository.read_page(relative)
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(page.content, encoding="utf-8")
            baseline[relative] = _sha256(page.content.encode())
        manifest = {"run_id": run_id, "files": baseline}
        (root / "run-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return cls(root, layout, baseline)

    def relative_files(self) -> set[str]:
        return {
            path.relative_to(self.root).as_posix()
            for path in self.root.rglob("*")
            if path.is_file() or path.is_symlink()
        }

    def write_text(self, relative_path: str, content: str) -> None:
        path = self._path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def write_bytes(self, relative_path: str, content: bytes) -> None:
        path = self._path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def collect_diff(self) -> list[WorkspaceDiff]:
        current: dict[str, tuple[str, str]] = {}
        for path in self.root.rglob("*"):
            if path.is_symlink():
                raise AgentWorkspaceViolation("workspace symlinks are forbidden")
            if not path.is_file():
                continue
            relative = path.relative_to(self.root).as_posix()
            if relative == "run-manifest.json":
                continue
            if path.suffix != ".md":
                raise AgentWorkspaceViolation(f"non-Markdown file: {relative}")
            payload = path.read_bytes()
            if b"\x00" in payload:
                raise AgentWorkspaceViolation(f"binary file: {relative}")
            try:
                content = payload.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise AgentWorkspaceViolation(f"non-UTF-8 file: {relative}") from exc
            current[relative] = (_sha256(payload), content)

        deleted = set(self.baseline) - set(current)
        created = set(current) - set(self.baseline)
        diffs: list[WorkspaceDiff] = []
        for old_path in sorted(deleted):
            old_hash = self.baseline[old_path]
            renamed = next((path for path in sorted(created) if current[path][0] == old_hash), None)
            if (
                renamed is None
                or not old_path.startswith("wiki/")
                or not renamed.startswith("wiki/")
            ):
                raise AgentWorkspaceViolation(f"deleted file: {old_path}")
            created.remove(renamed)
            diffs.append(
                WorkspaceDiff(
                    action="rename",
                    path=renamed,
                    old_path=old_path,
                    before=(self.layout.root / old_path).read_text(encoding="utf-8"),
                    after=current[renamed][1],
                )
            )
        for relative_path in sorted(created):
            if not relative_path.startswith("wiki/") or not relative_path.endswith(".md"):
                raise AgentWorkspaceViolation(f"out-of-scope file: {relative_path}")
            diffs.append(WorkspaceDiff("create", relative_path, None, current[relative_path][1]))
        for relative_path in sorted(set(current) & set(self.baseline)):
            if current[relative_path][0] == self.baseline[relative_path]:
                continue
            if not relative_path.startswith("wiki/"):
                raise AgentWorkspaceViolation(f"read-only context changed: {relative_path}")
            before = (self.layout.root / relative_path).read_text(encoding="utf-8")
            diffs.append(WorkspaceDiff("update", relative_path, before, current[relative_path][1]))
        return diffs

    def cleanup(self) -> None:
        shutil.rmtree(self.root.parent, ignore_errors=True)

    def _path(self, relative_path: str) -> Path:
        supplied = PurePosixPath(relative_path)
        if supplied.is_absolute() or ".." in supplied.parts:
            raise AgentWorkspaceViolation("unsafe workspace path")
        path = (self.root / relative_path).resolve(strict=False)
        if not path.is_relative_to(self.root.resolve()):
            raise AgentWorkspaceViolation("workspace path escape")
        return path


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
