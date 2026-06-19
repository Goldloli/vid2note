from datetime import UTC, datetime

from vid2note_core.source.registrar import SourceRegistration
from vid2note_core.vault.repository import content_hash
from vid2note_core.wiki.models import ChangeOperation, ChangeSet, Citation


def _pending_changeset(client, tmp_path, *, changeset_id="chg_0123456789ab", include_second=False):
    services = client.app.state.services
    srt = tmp_path / f"{changeset_id}.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:05,000\nNew claim.\n", encoding="utf-8")
    note = tmp_path / f"{changeset_id}.md"
    note.write_text("# Evidence\n", encoding="utf-8")
    source = services.source_registrar.register(
        SourceRegistration(
            task_id="task_0123456789ab",
            canonical_url=f"https://example.com/{changeset_id}",
            title="Source",
            imported_at=datetime(2026, 6, 18, tzinfo=UTC),
            srt_path=srt,
            note_path=note,
            duration_ms=5000,
        )
    )
    page_path = services.vault_layout.wiki / "concepts" / "approval-topic.md"
    before = (
        "---\nid: concept_approval_topic\ntitle: Approval Topic\n"
        "page_type: concept\nstatus: active\n"
        f"sources:\n  - {source.source_id}\n"
        "created_at: 2026-06-18\nupdated_at: 2026-06-19\n---\n\n"
        "# Approval Topic\n\nOld claim.\n"
    )
    page_path.write_text(before, encoding="utf-8")
    operations = [
        ChangeOperation(
            page_id="concept_approval_topic",
            path="wiki/concepts/approval-topic.md",
            base_hash=content_hash(before),
            action="update",
            before=before,
            after=before.replace("Old claim.", "New claim 42."),
            rationale="New evidence",
            citations=[Citation(source_id=source.source_id, start_ms=1000, end_ms=5000)],
        )
    ]
    if include_second:
        operations.append(
            ChangeOperation(
                page_id="concept_unselected",
                path="wiki/concepts/unselected.md",
                action="create",
                after=before.replace("concept_approval_topic", "concept_unselected").replace(
                    "Approval Topic", "Unselected"
                ),
                rationale="Second operation",
                citations=[Citation(source_id=source.source_id, start_ms=1000, end_ms=5000)],
            )
        )
    changeset = ChangeSet(
        id=changeset_id,
        created_at=datetime(2026, 6, 19, tzinfo=UTC),
        source_ids=[source.source_id],
        base_revision="rev-1",
        agent_runtime="built-in",
        summary="Approve a new claim",
        operations=operations,
        contradictions=[],
    )
    services.changesets.save_pending(changeset)
    return changeset


def test_changeset_list_get_and_approve_applies_wiki(client, tmp_path):
    changeset = _pending_changeset(client, tmp_path)

    listed = client.get("/api/v1/changesets", params={"status": "pending"})
    loaded = client.get(f"/api/v1/changesets/{changeset.id}")
    approved = client.post(f"/api/v1/changesets/{changeset.id}/approve", json={})

    assert listed.status_code == 200
    assert listed.json()[0]["id"] == changeset.id
    assert loaded.json()["operations"][0]["citations"][0]["start_ms"] == 1000
    assert approved.status_code == 200
    assert approved.json()["status"] == "applied"
    page = client.get(
        "/api/v1/vault/page", params={"path": "wiki/concepts/approval-topic.md"}
    ).json()
    assert "New claim 42" in page["content"]


def test_changeset_reject_blocks_later_approval(client, tmp_path):
    changeset = _pending_changeset(client, tmp_path, changeset_id="chg_abcdef012345")

    rejected = client.post(
        f"/api/v1/changesets/{changeset.id}/reject", json={"reason": "not relevant"}
    )
    approved = client.post(f"/api/v1/changesets/{changeset.id}/approve", json={})

    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert approved.status_code == 409


def test_partial_approval_applies_only_selected_operations(client, tmp_path):
    changeset = _pending_changeset(
        client,
        tmp_path,
        changeset_id="chg_112233445566",
        include_second=True,
    )

    approved = client.post(
        f"/api/v1/changesets/{changeset.id}/approve",
        json={"operation_indexes": [0]},
    )

    assert approved.status_code == 200
    assert approved.json()["parent_id"] == changeset.id
    assert len(approved.json()["operations"]) == 1
    assert not (client.app.state.services.vault_layout.wiki / "concepts" / "unselected.md").exists()
    assert client.app.state.services.changesets.get(changeset.id).status == "pending"


def test_changeset_revise_supersedes_pending_proposal(client, tmp_path):
    changeset = _pending_changeset(client, tmp_path, changeset_id="chg_aabbccddeeff")

    revised = client.post(
        f"/api/v1/changesets/{changeset.id}/revise",
        json={
            "summary": "Revised summary",
            "operations": [operation.model_dump(mode="json") for operation in changeset.operations],
            "contradictions": [],
        },
    )

    assert revised.status_code == 200
    assert revised.json()["supersedes"] == changeset.id
    assert revised.json()["status"] == "pending"


def test_changeset_revert_restores_page(client, tmp_path):
    changeset = _pending_changeset(client, tmp_path, changeset_id="chg_66778899aabb")
    client.post(f"/api/v1/changesets/{changeset.id}/approve", json={})

    reverted = client.post(f"/api/v1/changesets/{changeset.id}/revert")

    assert reverted.status_code == 200
    assert reverted.json()["status"] == "reverted"
    listed = client.get("/api/v1/changesets", params={"status": "reverted"})
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [changeset.id]
    page = client.get(
        "/api/v1/vault/page", params={"path": "wiki/concepts/approval-topic.md"}
    ).json()
    assert "Old claim" in page["content"]


def test_autonomy_mode_uses_config_and_defaults_to_approval(client):
    initial = client.get("/api/v1/wiki/policy")
    updated = client.put("/api/v1/wiki/policy", json={"mode": "auto-revertible"})
    config = client.get("/api/v1/config")

    assert initial.json()["mode"] == "approval"
    assert updated.json()["mode"] == "auto-revertible"
    assert config.json()["autonomy_mode"] == "auto-revertible"
