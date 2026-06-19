import json

from vid2note_core.vault.layout import VaultLayout
from vid2note_core.vault.repository import content_hash
from vid2note_core.vault.watcher import VaultWatcher


def _external_entries(layout):
    return [
        json.loads(line)
        for line in layout.log.read_text(encoding="utf-8").splitlines()
        if line.startswith("{") and '"external-edit"' in line
    ]


def test_multiple_save_events_are_debounced_into_one_external_edit(tmp_path):
    layout = VaultLayout.initialize(tmp_path / "vault")
    page = layout.wiki / "concepts" / "debounce.md"
    page.write_text("first", encoding="utf-8")
    watcher = VaultWatcher(layout, debounce_seconds=0.5)
    watcher.initialize()

    page.write_text("second", encoding="utf-8")
    watcher.poll_once(now=1.0)
    page.write_text("third", encoding="utf-8")
    watcher.poll_once(now=1.2)
    watcher.poll_once(now=1.8)

    entries = _external_entries(layout)
    assert len(entries) == 1
    assert entries[0]["path"] == "wiki/concepts/debounce.md"
    assert entries[0]["after_hash"] == content_hash("third")


def test_private_cache_and_internal_edit_are_not_logged(tmp_path):
    layout = VaultLayout.initialize(tmp_path / "vault")
    watcher = VaultWatcher(layout, debounce_seconds=0)
    watcher.initialize()
    cached = layout.private / "cache" / "frames" / "ignored.md"
    cached.write_text("cache", encoding="utf-8")
    page = layout.wiki / "concepts" / "internal.md"
    page.write_text("application write", encoding="utf-8")
    watcher.ignore(
        "wiki/concepts/internal.md",
        content_hash("application write"),
        operation_id="op-1",
    )

    watcher.poll_once(now=1.0)
    watcher.poll_once(now=1.1)

    assert _external_entries(layout) == []
