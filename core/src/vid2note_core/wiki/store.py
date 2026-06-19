from __future__ import annotations

import os
import re
from pathlib import Path

from vid2note_core.wiki.models import ChangeSet

_CHANGESET_ID = re.compile(r"^chg_[a-f0-9]{12}$")


class InvalidChangeSetTransition(ValueError):  # noqa: N818 - domain transition name
    pass


class ChangeSetStore:
    def __init__(self, vault_root: str | Path):
        self.root = Path(vault_root).expanduser().resolve() / ".vid2note" / "changes"
        self.pending = self.root / "pending"
        self.applied = self.root / "applied"
        self.rejected = self.root / "rejected"
        for directory in (self.pending, self.applied, self.rejected):
            directory.mkdir(parents=True, exist_ok=True)

    def save_pending(self, changeset: ChangeSet) -> None:
        if changeset.status != "pending":
            raise InvalidChangeSetTransition("only pending ChangeSets can be saved as pending")
        self._write_new(self.pending / f"{changeset.id}.json", changeset)

    def get(self, changeset_id: str) -> ChangeSet | None:
        self._validate_id(changeset_id)
        for directory in (self.applied, self.rejected, self.pending):
            path = directory / f"{changeset_id}.json"
            if path.is_file():
                return ChangeSet.model_validate_json(path.read_text(encoding="utf-8"))
        return None

    def list(self, status: str = "pending") -> list[ChangeSet]:
        directory = self._status_directory(status)
        return [
            ChangeSet.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(directory.glob("chg_*.json"))
        ]

    def reject(self, changeset_id: str, *, reason: str) -> ChangeSet:
        return self._transition(changeset_id, "rejected", rejection_reason=reason)

    def mark_applied(self, changeset_id: str) -> ChangeSet:
        return self._transition(changeset_id, "applied")

    def mark_reverted(self, changeset_id: str) -> ChangeSet:
        changeset = self.get(changeset_id)
        if changeset is None or changeset.status != "applied":
            raise InvalidChangeSetTransition(
                f"cannot revert ChangeSet in {getattr(changeset, 'status', None)}"
            )
        source = self.applied / f"{changeset_id}.json"
        reverted = changeset.model_copy(update={"status": "reverted"})
        temporary = self.applied / f".{changeset_id}.reverted"
        self._write_new(temporary, reverted)
        os.replace(temporary, source)
        self._fsync_directory(self.applied)
        return reverted

    def _transition(self, changeset_id: str, status: str, **updates: str) -> ChangeSet:
        changeset = self.get(changeset_id)
        if changeset is None or changeset.status != "pending":
            raise InvalidChangeSetTransition(
                f"cannot transition ChangeSet in {getattr(changeset, 'status', None)}"
            )
        destination_directory = self._status_directory(status)
        transitioned = changeset.model_copy(update={"status": status, **updates})
        destination = destination_directory / f"{changeset_id}.json"
        self._write_new(destination, transitioned)
        (self.pending / f"{changeset_id}.json").unlink()
        self._fsync_directory(self.pending)
        return transitioned

    @staticmethod
    def _write_new(path: Path, changeset: ChangeSet) -> None:
        payload = (changeset.model_dump_json(indent=2) + "\n").encode()
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        ChangeSetStore._fsync_directory(path.parent)

    def _status_directory(self, status: str) -> Path:
        directories = {
            "pending": self.pending,
            "applied": self.applied,
            "rejected": self.rejected,
        }
        try:
            return directories[status]
        except KeyError as exc:
            raise ValueError(f"unsupported ChangeSet status: {status}") from exc

    @staticmethod
    def _validate_id(changeset_id: str) -> None:
        if not _CHANGESET_ID.fullmatch(changeset_id):
            raise ValueError("invalid ChangeSet id")

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
