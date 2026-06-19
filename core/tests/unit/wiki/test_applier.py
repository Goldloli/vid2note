import json
import os
from datetime import UTC, datetime

import pytest
from vid2note_core.source.registrar import SourceRegistrar, SourceRegistration
from vid2note_core.vault.layout import VaultLayout
from vid2note_core.vault.repository import VaultRepository, content_hash
from vid2note_core.wiki.applier import ChangeSetApplier
from vid2note_core.wiki.models import ChangeOperation, ChangeSet, Citation
from vid2note_core.wiki.store import ChangeSetStore
from vid2note_core.wiki.validator import ChangeSetValidator


def _page(source_id: str, claim: str) -> str:
    return (
        "---\n"
        "id: concept_topic\n"
        "title: Topic\n"
        "page_type: concept\n"
        "status: active\n"
        f"sources:\n  - {source_id}\n"
        "created_at: 2026-06-18\n"
        "updated_at: 2026-06-19\n"
        "---\n\n"
        "# Topic\n\n"
        f"{claim}\n"
    )


@pytest.fixture
def setup_applier(tmp_path):
    layout = VaultLayout.initialize(tmp_path / "vault")
    srt = tmp_path / "source.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:05,000\nNew claim.\n", encoding="utf-8")
    note = tmp_path / "note.md"
    note.write_text("# Evidence\n", encoding="utf-8")
    source = SourceRegistrar(layout).register(
        SourceRegistration(
            task_id="task_0123456789ab",
            canonical_url="https://example.com/source",
            title="Source",
            imported_at=datetime(2026, 6, 18, tzinfo=UTC),
            srt_path=srt,
            note_path=note,
            duration_ms=5000,
        )
    )
    page_path = layout.wiki / "concepts" / "topic.md"
    before = _page(source.source_id, "Old claim.")
    after = _page(source.source_id, "New claim 42.")
    page_path.write_text(before, encoding="utf-8")
    changeset = ChangeSet(
        id="chg_0123456789ab",
        created_at=datetime(2026, 6, 19, tzinfo=UTC),
        source_ids=[source.source_id],
        base_revision="rev-1",
        agent_runtime="built-in",
        summary="Update topic",
        operations=[
            ChangeOperation(
                page_id="concept_topic",
                path="wiki/concepts/topic.md",
                base_hash=content_hash(before),
                action="update",
                before=before,
                after=after,
                rationale="New source",
                citations=[Citation(source_id=source.source_id, start_ms=1000, end_ms=5000)],
            )
        ],
        contradictions=[],
    )
    repository = VaultRepository(layout)
    store = ChangeSetStore(layout.root)
    store.save_pending(changeset)
    applier = ChangeSetApplier(
        layout,
        repository,
        store,
        ChangeSetValidator(layout, repository),
    )
    return layout, repository, store, applier, changeset


def _live_bytes(layout):
    paths = [layout.wiki / "concepts" / "topic.md", layout.index, layout.log]
    return {path.relative_to(layout.root).as_posix(): path.read_bytes() for path in paths}


def test_apply_failure_leaves_all_live_files_unchanged(setup_applier):
    layout, repository, store, _, changeset = setup_applier
    before = _live_bytes(layout)
    replacements = 0

    def fail_after_first(source, destination):
        nonlocal replacements
        replacements += 1
        if replacements == 2:
            raise OSError("injected replacement failure")
        os.replace(source, destination)

    applier = ChangeSetApplier(
        layout,
        repository,
        store,
        ChangeSetValidator(layout, repository),
        replace=fail_after_first,
    )

    with pytest.raises(OSError, match="injected"):
        applier.apply(changeset)

    assert _live_bytes(layout) == before
    assert store.get(changeset.id).status == "pending"


def test_apply_updates_pages_index_and_log_together(setup_applier):
    layout, repository, store, applier, changeset = setup_applier

    applied = applier.apply(changeset)

    assert "New claim 42" in repository.read_page("wiki/concepts/topic.md").content
    assert "Topic" in repository.read_page("index.md").content
    assert changeset.id in repository.read_page("log.md").content
    assert applied.status == "applied"
    assert store.get(changeset.id).status == "applied"


def test_revert_restores_exact_pre_apply_bytes(setup_applier):
    layout, _, store, applier, changeset = setup_applier
    before = _live_bytes(layout)
    applier.apply(changeset)

    reverted = applier.revert(changeset.id)

    assert _live_bytes(layout) == before
    assert reverted.status == "reverted"
    assert store.get(changeset.id).status == "reverted"


def test_recovery_restores_incomplete_transaction(setup_applier):
    layout, _, _, applier, changeset = setup_applier
    before = _live_bytes(layout)
    transaction = layout.private / "transactions" / changeset.id
    before_dir = transaction / "before"
    before_dir.mkdir(parents=True)
    for relative, payload in before.items():
        destination = before_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    page = layout.wiki / "concepts" / "topic.md"
    page.write_text("partial", encoding="utf-8")
    (transaction / "manifest.json").write_text(
        json.dumps(
            {
                "changeset_id": changeset.id,
                "status": "committing",
                "paths": [
                    {"path": path, "existed": True, "committed": path.endswith("topic.md")}
                    for path in before
                ],
            }
        ),
        encoding="utf-8",
    )

    recovered = applier.recover_incomplete()

    assert recovered == [changeset.id]
    assert page.read_bytes() == before["wiki/concepts/topic.md"]
    assert "transaction-recovered" in layout.log.read_text(encoding="utf-8")


def test_revert_conflict_creates_pending_proposal_without_overwrite(setup_applier):
    layout, _, store, applier, changeset = setup_applier
    applier.apply(changeset)
    page = layout.wiki / "concepts" / "topic.md"
    external = page.read_text(encoding="utf-8") + "\nHuman edit.\n"
    page.write_text(external, encoding="utf-8")

    proposal = applier.revert(changeset.id)

    assert proposal.status == "pending"
    assert proposal.parent_id == changeset.id
    assert page.read_text(encoding="utf-8") == external
    assert store.get(changeset.id).status == "applied"
