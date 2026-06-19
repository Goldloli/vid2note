from datetime import UTC, datetime

import pytest
from vid2note_core.wiki.models import ChangeOperation, ChangeSet, Citation
from vid2note_core.wiki.store import ChangeSetStore, InvalidChangeSetTransition


@pytest.fixture
def changeset():
    return ChangeSet(
        id="chg_0123456789ab",
        created_at=datetime(2026, 6, 19, tzinfo=UTC),
        source_ids=["src_20260618_01234567"],
        base_revision="rev-1",
        agent_runtime="built-in",
        summary="Create page",
        operations=[
            ChangeOperation(
                page_id="concept_poc_trap",
                path="wiki/concepts/poc-trap.md",
                action="create",
                after="# POC Trap\n",
                rationale="New evidence",
                citations=[Citation(source_id="src_20260618_01234567", start_ms=1000, end_ms=3000)],
            )
        ],
        contradictions=[],
    )


def test_changeset_round_trip_preserves_operations_and_citations(tmp_path, changeset):
    store = ChangeSetStore(tmp_path)

    store.save_pending(changeset)

    assert store.get(changeset.id) == changeset


def test_changeset_cannot_apply_after_rejection(tmp_path, changeset):
    store = ChangeSetStore(tmp_path)
    store.save_pending(changeset)
    rejected = store.reject(changeset.id, reason="not relevant")

    assert rejected.status == "rejected"
    with pytest.raises(InvalidChangeSetTransition):
        store.mark_applied(changeset.id)


def test_pending_file_is_append_safe(tmp_path, changeset):
    store = ChangeSetStore(tmp_path)
    store.save_pending(changeset)

    with pytest.raises(FileExistsError):
        store.save_pending(changeset)


def test_rejection_preserves_reason_without_mutating_original_file(tmp_path, changeset):
    store = ChangeSetStore(tmp_path)
    store.save_pending(changeset)
    pending_bytes = (store.pending / f"{changeset.id}.json").read_bytes()

    rejected = store.reject(changeset.id, reason="not relevant")

    assert rejected.rejection_reason == "not relevant"
    assert not (store.pending / f"{changeset.id}.json").exists()
    assert pending_bytes != (store.rejected / f"{changeset.id}.json").read_bytes()


def test_reverted_changeset_is_not_listed_as_applied(tmp_path, changeset):
    store = ChangeSetStore(tmp_path)
    store.save_pending(changeset)
    store.mark_applied(changeset.id)

    reverted = store.mark_reverted(changeset.id)

    assert reverted.status == "reverted"
    assert store.list("applied") == []
    assert store.list("reverted") == [reverted]
