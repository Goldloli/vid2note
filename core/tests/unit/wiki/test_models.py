from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from vid2note_core.wiki.models import ChangeSet


def changeset_payload():
    return {
        "id": "chg_0123456789ab",
        "created_at": datetime(2026, 6, 19, tzinfo=UTC),
        "source_ids": ["src_20260618_01234567"],
        "base_revision": "rev-1",
        "agent_runtime": "built-in",
        "summary": "Create a concept page",
        "operations": [
            {
                "page_id": "concept_poc_trap",
                "path": "wiki/concepts/poc-trap.md",
                "base_hash": None,
                "action": "create",
                "before": None,
                "after": "---\nid: concept_poc_trap\ntype: concept\n---\n\n# POC Trap\n",
                "rationale": "New supported concept",
                "citations": [
                    {"source_id": "src_20260618_01234567", "start_ms": 1000, "end_ms": 3000}
                ],
            }
        ],
        "contradictions": [],
    }


def test_changeset_requires_at_least_one_operation():
    payload = changeset_payload()
    payload["operations"] = []

    with pytest.raises(ValidationError):
        ChangeSet.model_validate(payload)


def test_citation_requires_ordered_time_range():
    payload = changeset_payload()
    payload["operations"][0]["citations"][0]["end_ms"] = 500

    with pytest.raises(ValidationError, match="end_ms"):
        ChangeSet.model_validate(payload)


def test_changeset_is_immutable():
    changeset = ChangeSet.model_validate(changeset_payload())

    with pytest.raises(ValidationError):
        changeset.status = "applied"
