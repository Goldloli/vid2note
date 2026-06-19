from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from vid2note_core.vault.layout import VaultLayout
from vid2note_core.vault.log import VaultLog

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FileState:
    mtime_ns: int
    size: int
    content_hash: str


@dataclass(slots=True)
class PendingEdit:
    before_hash: str
    after_hash: str
    changed_at: float


class VaultWatcher:
    def __init__(
        self,
        layout: VaultLayout,
        *,
        interval_seconds: float = 1.0,
        debounce_seconds: float = 0.5,
    ):
        self.layout = layout
        self.root = layout.root.resolve()
        self.interval_seconds = interval_seconds
        self.debounce_seconds = debounce_seconds
        self.log = VaultLog(layout.log)
        self._snapshot: dict[str, FileState] = {}
        self._pending: dict[str, PendingEdit] = {}
        self._ignored: dict[tuple[str, str], str] = {}
        self._lock = threading.Lock()
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    def initialize(self) -> None:
        with self._lock:
            self._snapshot = self._scan()
            self._pending.clear()

    def ignore(self, path: str, after_hash: str, operation_id: str) -> None:
        with self._lock:
            self._ignored[(path, after_hash)] = operation_id
            pending = self._pending.get(path)
            if pending is not None and pending.after_hash == after_hash:
                del self._pending[path]

    def poll_once(self, *, now: float | None = None) -> None:
        observed_at = time.monotonic() if now is None else now
        current = self._scan()
        with self._lock:
            for path in sorted(set(self._snapshot) | set(current)):
                before = self._snapshot.get(path)
                after = current.get(path)
                before_hash = before.content_hash if before is not None else ""
                after_hash = after.content_hash if after is not None else ""
                if before_hash == after_hash:
                    continue
                ignored_key = (path, after_hash)
                if ignored_key in self._ignored:
                    del self._ignored[ignored_key]
                    self._pending.pop(path, None)
                    continue
                pending = self._pending.get(path)
                if pending is None:
                    self._pending[path] = PendingEdit(before_hash, after_hash, observed_at)
                else:
                    pending.after_hash = after_hash
                    pending.changed_at = observed_at
            self._snapshot = current
            ready = [
                path
                for path, edit in self._pending.items()
                if observed_at - edit.changed_at >= self.debounce_seconds
            ]
            for path in ready:
                edit = self._pending.pop(path)
                self.log.append_edit(
                    operation="external-edit",
                    path=path,
                    before_hash=edit.before_hash,
                    after_hash=edit.after_hash,
                )

    async def start(self) -> None:
        if self._running:
            return
        self.initialize()
        self._running = True
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._stop_event.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _loop(self) -> None:
        while self._running:
            try:
                await asyncio.to_thread(self.poll_once)
            except Exception:  # noqa: BLE001 - watcher failure must not stop the application
                logger.exception("Vault watcher poll failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)

    def _scan(self) -> dict[str, FileState]:
        snapshot: dict[str, FileState] = {}
        for candidate in self.root.rglob("*.md"):
            try:
                relative = candidate.relative_to(self.root)
                if ".vid2note" in relative.parts or relative.as_posix() == "log.md":
                    continue
                if candidate.name.startswith("."):
                    continue
                resolved = candidate.resolve()
                if not resolved.is_file() or not resolved.is_relative_to(self.root):
                    continue
                stat = resolved.stat()
                snapshot[relative.as_posix()] = FileState(
                    mtime_ns=stat.st_mtime_ns,
                    size=stat.st_size,
                    content_hash=_sha256(resolved),
                )
            except OSError:
                continue
        return snapshot


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
