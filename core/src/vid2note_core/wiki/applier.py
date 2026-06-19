from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import yaml

from vid2note_core.vault.layout import VaultLayout
from vid2note_core.vault.repository import VaultRepository, content_hash
from vid2note_core.wiki.index import IndexEntry, PageType, parse_index, render_index
from vid2note_core.wiki.models import ChangeOperation, ChangeSet
from vid2note_core.wiki.store import ChangeSetStore
from vid2note_core.wiki.validator import ChangeSetValidator


class ChangeSetValidationError(ValueError):
    pass


class ChangeSetApplier:
    def __init__(
        self,
        layout: VaultLayout,
        repository: VaultRepository,
        store: ChangeSetStore,
        validator: ChangeSetValidator,
        *,
        replace: Callable[[str | Path, str | Path], None] = os.replace,
    ):
        self.layout = layout
        self.repository = repository
        self.store = store
        self.validator = validator
        self.replace = replace
        self.transactions = layout.private / "transactions"
        self.transactions.mkdir(parents=True, exist_ok=True)
        self.internal_edit_observer: Callable[[str, str, str], None] | None = None

    def apply(self, changeset: ChangeSet) -> ChangeSet:
        stored = self.store.get(changeset.id)
        if stored is None or stored.status != "pending" or stored != changeset:
            raise ValueError("ChangeSet must match its pending stored representation")
        validation = self.validator.validate(changeset)
        if not validation.valid:
            codes = ", ".join(
                issue.code for issue in validation.issues if issue.severity == "error"
            )
            raise ChangeSetValidationError(codes)

        transaction = self.transactions / changeset.id
        if transaction.exists():
            manifest = self._read_manifest(transaction)
            if manifest.get("status") not in {"rolled_back", "recovered"}:
                raise FileExistsError(transaction)
            shutil.rmtree(transaction)
        before_dir = transaction / "before"
        after_dir = transaction / "after"
        before_dir.mkdir(parents=True)
        after_dir.mkdir()

        after_payloads = self._build_after_payloads(changeset)
        paths = sorted(after_payloads)
        manifest = {
            "changeset_id": changeset.id,
            "status": "prepared",
            "paths": [],
        }
        for relative_path in paths:
            live = self.layout.root / relative_path
            existed = live.is_file()
            if existed:
                self._write_snapshot(before_dir / relative_path, live.read_bytes())
            payload = after_payloads[relative_path]
            if payload is not None:
                self._write_snapshot(after_dir / relative_path, payload)
            manifest["paths"].append(
                {
                    "path": relative_path,
                    "existed": existed,
                    "delete": payload is None,
                    "committed": False,
                }
            )
        self._write_manifest(transaction, manifest)

        manifest["status"] = "committing"
        self._write_manifest(transaction, manifest)
        try:
            for item in manifest["paths"]:
                relative_path = item["path"]
                live = self.layout.root / relative_path
                if item["delete"]:
                    live.unlink(missing_ok=True)
                    _fsync_directory(live.parent)
                else:
                    self._replace_live(after_dir / relative_path, live)
                item["committed"] = True
                self._write_manifest(transaction, manifest)
        except Exception:
            self._restore_before(transaction, manifest)
            manifest["status"] = "rolled_back"
            self._write_manifest(transaction, manifest)
            raise

        manifest["status"] = "live_committed"
        self._write_manifest(transaction, manifest)
        try:
            applied = self.store.mark_applied(changeset.id)
        except Exception:
            persisted = self.store.get(changeset.id)
            if persisted is not None and persisted.status == "applied":
                manifest["status"] = "committed"
                self._write_manifest(transaction, manifest)
                self._notify_internal(paths, changeset.id)
                return persisted
            self._restore_before(transaction, manifest)
            manifest["status"] = "rolled_back"
            self._write_manifest(transaction, manifest)
            raise
        manifest["status"] = "committed"
        self._write_manifest(transaction, manifest)
        self._notify_internal(paths, changeset.id)
        return applied

    def revert(self, changeset_id: str) -> ChangeSet:
        changeset = self.store.get(changeset_id)
        if changeset is None or changeset.status != "applied":
            raise ValueError("only applied ChangeSets can be reverted")
        transaction = self.transactions / changeset_id
        manifest = self._read_manifest(transaction)
        conflicts = []
        for item in manifest["paths"]:
            relative_path = item["path"]
            live = self.layout.root / relative_path
            after = transaction / "after" / relative_path
            if item.get("delete", False):
                conflict = live.exists()
            else:
                conflict = not live.is_file() or _sha256(live.read_bytes()) != _sha256(
                    after.read_bytes()
                )
            if conflict:
                conflicts.append(relative_path)
        if conflicts:
            return self._create_revert_proposal(changeset, transaction)

        self._restore_before(transaction, manifest)
        try:
            reverted = self.store.mark_reverted(changeset_id)
        except Exception:
            persisted = self.store.get(changeset_id)
            if persisted is not None and persisted.status == "reverted":
                reverted = persisted
            else:
                self._restore_after(transaction, manifest)
                manifest["status"] = "committed"
                self._write_manifest(transaction, manifest)
                raise
        manifest["status"] = "reverted"
        self._write_manifest(transaction, manifest)
        self._notify_internal(
            [
                item["path"]
                for item in manifest["paths"]
                if (self.layout.root / item["path"]).is_file()
            ],
            f"revert:{changeset_id}",
        )
        return reverted

    def recover_incomplete(self) -> list[str]:
        recovered: list[str] = []
        for transaction in sorted(self.transactions.iterdir()):
            if not transaction.is_dir() or not (transaction / "manifest.json").is_file():
                continue
            manifest = self._read_manifest(transaction)
            status = manifest.get("status")
            if status in {"committed", "rolled_back", "recovered", "reverted"}:
                continue
            changeset_id = str(manifest["changeset_id"])
            if status == "live_committed":
                stored = self.store.get(changeset_id)
                if stored is not None and stored.status == "pending":
                    self.store.mark_applied(changeset_id)
                manifest["status"] = "committed"
            else:
                self._restore_before(transaction, manifest)
                manifest["status"] = "recovered"
                with self.layout.log.open("a", encoding="utf-8") as log:
                    log.write(f"\n- transaction-recovered `{changeset_id}`\n")
                    log.flush()
                    os.fsync(log.fileno())
            self._write_manifest(transaction, manifest)
            recovered.append(changeset_id)
        return recovered

    def _build_after_payloads(self, changeset: ChangeSet) -> dict[str, bytes | None]:
        payloads: dict[str, bytes | None] = {
            operation.path: operation.after.encode("utf-8") for operation in changeset.operations
        }
        current_index = self.layout.index.read_text(encoding="utf-8")
        entries = parse_index(current_index)
        by_page_id: dict[str, IndexEntry] = {}
        for entry in entries:
            try:
                page = self.repository.read_page(entry.path)
            except (FileNotFoundError, OSError):
                continue
            page_id = (page.frontmatter or {}).get("id", entry.page_id)
            by_page_id[str(page_id)] = entry
        for operation in changeset.operations:
            previous = by_page_id.get(operation.page_id)
            if (
                operation.action == "rename"
                and previous is not None
                and previous.path != operation.path
            ):
                payloads[previous.path] = None
            frontmatter = _frontmatter(operation.after)
            page_type = cast(PageType, frontmatter["page_type"])
            sources = frontmatter.get("sources", [])
            updated_raw = frontmatter.get("updated_at", changeset.created_at.date())
            updated = (
                updated_raw
                if isinstance(updated_raw, date)
                else date.fromisoformat(str(updated_raw))
            )
            by_page_id[operation.page_id] = IndexEntry(
                page_id=operation.page_id,
                title=str(frontmatter["title"]),
                path=operation.path,
                summary=operation.rationale,
                page_type=page_type,
                source_count=len(set(sources)) if isinstance(sources, list) else 0,
                updated=updated,
            )
        payloads["index.md"] = render_index(
            list(by_page_id.values()), existing=current_index
        ).encode("utf-8")
        current_log = self.layout.log.read_text(encoding="utf-8")
        audit = (
            f"\n- {datetime.now(UTC).isoformat()} changeset `{changeset.id}` applied: "
            f"{changeset.summary}\n"
        )
        payloads["log.md"] = (current_log.rstrip() + audit).encode("utf-8")
        return payloads

    def _create_revert_proposal(self, changeset: ChangeSet, transaction: Path) -> ChangeSet:
        operations: list[ChangeOperation] = []
        original_by_path = {operation.path: operation for operation in changeset.operations}
        for relative_path, original in original_by_path.items():
            before_snapshot = transaction / "before" / relative_path
            if not before_snapshot.is_file():
                raise ChangeSetValidationError(
                    "A create operation cannot be safely reverted after external edits"
                )
            live_content = (self.layout.root / relative_path).read_text(encoding="utf-8")
            operations.append(
                original.model_copy(
                    update={
                        "base_hash": content_hash(live_content),
                        "before": live_content,
                        "after": before_snapshot.read_text(encoding="utf-8"),
                        "rationale": f"Revert {changeset.id} without overwriting external edits",
                    }
                )
            )
        material = (
            changeset.id + "|" + "|".join(operation.base_hash or "" for operation in operations)
        )
        proposal = ChangeSet(
            id=f"chg_{hashlib.sha256(material.encode()).hexdigest()[:12]}",
            created_at=datetime.now(UTC),
            source_ids=changeset.source_ids,
            base_revision=changeset.id,
            agent_runtime="revert",
            summary=f"Review revert of {changeset.id}",
            operations=operations,
            contradictions=[],
            parent_id=changeset.id,
        )
        existing = self.store.get(proposal.id)
        if existing is None:
            self.store.save_pending(proposal)
        return proposal

    def _restore_before(self, transaction: Path, manifest: dict) -> None:
        for item in reversed(manifest["paths"]):
            relative_path = item["path"]
            live = self.layout.root / relative_path
            before = transaction / "before" / relative_path
            if item["existed"]:
                self._replace_live(before, live, replace=os.replace)
            else:
                live.unlink(missing_ok=True)

    def _restore_after(self, transaction: Path, manifest: dict) -> None:
        for item in manifest["paths"]:
            live = self.layout.root / item["path"]
            if item.get("delete", False):
                live.unlink(missing_ok=True)
                _fsync_directory(live.parent)
            else:
                self._replace_live(transaction / "after" / item["path"], live, replace=os.replace)

    def _replace_live(
        self,
        snapshot: Path,
        live: Path,
        *,
        replace: Callable[[str | Path, str | Path], None] | None = None,
    ) -> None:
        live.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=live.parent, prefix=f".{live.name}.", suffix=".tmp"
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            shutil.copyfile(snapshot, temporary)
            with temporary.open("rb") as source:
                os.fsync(source.fileno())
            (replace or self.replace)(temporary, live)
            _fsync_directory(live.parent)
        finally:
            temporary.unlink(missing_ok=True)

    def _notify_internal(self, paths: list[str], operation_id: str) -> None:
        if self.internal_edit_observer is None:
            return
        for relative_path in paths:
            live = self.layout.root / relative_path
            if live.is_file() and live.suffix == ".md" and relative_path != "log.md":
                self.internal_edit_observer(
                    relative_path,
                    _sha256(live.read_bytes()),
                    operation_id,
                )

    @staticmethod
    def _write_snapshot(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())

    @staticmethod
    def _write_manifest(transaction: Path, manifest: dict) -> None:
        destination = transaction / "manifest.json"
        descriptor, temporary_name = tempfile.mkstemp(
            dir=transaction, prefix=".manifest.", suffix=".tmp"
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(manifest, output, ensure_ascii=False, sort_keys=True, indent=2)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, destination)
            _fsync_directory(transaction)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _read_manifest(transaction: Path) -> dict:
        return json.loads((transaction / "manifest.json").read_text(encoding="utf-8"))


def _frontmatter(content: str) -> dict[str, object]:
    payload, separator, _ = content.removeprefix("---\n").partition("\n---\n")
    if not separator:
        return {}
    parsed = yaml.safe_load(payload)
    return parsed if isinstance(parsed, dict) else {}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
