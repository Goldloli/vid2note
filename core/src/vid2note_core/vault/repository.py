from __future__ import annotations

import hashlib
import os
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path, PurePath

import yaml
from pydantic.types import JsonValue

from vid2note_core.vault.layout import VaultLayout
from vid2note_core.vault.log import VaultLog
from vid2note_core.vault.models import VaultConflict, VaultPage, VaultPathError


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _as_json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, list | tuple):
        return [_as_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _as_json_value(item) for key, item in value.items()}
    return str(value)


class VaultRepository:
    def __init__(self, layout: VaultLayout):
        self.layout = layout
        self.root = layout.root.resolve()
        self.log = VaultLog(layout.log)

    def _resolve(self, relative_path: str) -> tuple[Path, str]:
        supplied = Path(relative_path)
        if supplied.is_absolute() or ".." in PurePath(relative_path).parts:
            raise VaultPathError(relative_path)
        normalized = supplied.as_posix()
        if not normalized or normalized == "." or normalized.startswith(".vid2note/"):
            raise VaultPathError(relative_path)
        candidate = (self.root / normalized).resolve(strict=False)
        if not candidate.is_relative_to(self.root):
            raise VaultPathError(relative_path)
        if candidate.suffix.lower() != ".md":
            raise VaultPathError(relative_path)
        return candidate, normalized

    def read_page(self, relative_path: str) -> VaultPage:
        path, normalized = self._resolve(relative_path)
        content = path.read_text(encoding="utf-8")
        return VaultPage(
            path=normalized,
            content=content,
            content_hash=content_hash(content),
            modified_at=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
            frontmatter=self._parse_frontmatter(content),
        )

    def update_human(self, relative_path: str, content: str, *, base_hash: str) -> VaultPage:
        path, normalized = self._resolve(relative_path)
        current = self.read_page(normalized)
        if current.content_hash != base_hash:
            raise VaultConflict(normalized)

        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)

        updated = self.read_page(normalized)
        self.log.append_edit(
            operation="human-edit",
            path=normalized,
            before_hash=current.content_hash,
            after_hash=updated.content_hash,
        )
        return updated

    @staticmethod
    def _parse_frontmatter(content: str) -> dict[str, JsonValue] | None:
        if not content.startswith("---\n"):
            return None
        frontmatter_text, separator, _ = content[4:].partition("\n---\n")
        if not separator:
            return None
        raw = yaml.safe_load(frontmatter_text)
        if not isinstance(raw, dict):
            return None
        normalized = _as_json_value(raw)
        return normalized if isinstance(normalized, dict) else None
