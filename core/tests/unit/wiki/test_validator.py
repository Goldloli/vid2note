from datetime import UTC, datetime

import pytest
from vid2note_core.source.registrar import SourceRegistrar, SourceRegistration
from vid2note_core.vault.layout import VaultLayout
from vid2note_core.vault.repository import VaultRepository, content_hash
from vid2note_core.wiki.models import ChangeOperation, ChangeSet, Citation
from vid2note_core.wiki.validator import ChangeSetValidator


def _page(page_id: str = "concept_topic", page_type: str = "concept", body: str = "Old claim."):
    return (
        "---\n"
        f"id: {page_id}\n"
        "title: Topic\n"
        f"page_type: {page_type}\n"
        "status: active\n"
        "sources:\n  - src_20260618_placeholder\n"
        "created_at: 2026-06-18\n"
        "updated_at: 2026-06-19\n"
        "---\n\n"
        "# Topic\n\n"
        f"{body}\n"
    )


@pytest.fixture
def validator_setup(tmp_path):
    layout = VaultLayout.initialize(tmp_path / "vault")
    srt = tmp_path / "source.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:05,000\nEvidence.\n", encoding="utf-8")
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
    current = _page().replace("src_20260618_placeholder", source.source_id)
    page_path.write_text(current, encoding="utf-8")
    repository = VaultRepository(layout)
    operation = ChangeOperation(
        page_id="concept_topic",
        path="wiki/concepts/topic.md",
        base_hash=content_hash(current),
        action="update",
        before=current,
        after=current.replace("Old claim.", "New claim 42."),
        rationale="New evidence",
        citations=[Citation(source_id=source.source_id, start_ms=1000, end_ms=5000)],
    )
    changeset = ChangeSet(
        id="chg_0123456789ab",
        created_at=datetime(2026, 6, 19, tzinfo=UTC),
        source_ids=[source.source_id],
        base_revision="rev-1",
        agent_runtime="built-in",
        summary="Update topic",
        operations=[operation],
        contradictions=[],
    )
    return ChangeSetValidator(layout, repository), changeset, current, source


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (lambda op, current: op.model_copy(update={"base_hash": "stale"}), "STALE_BASE_HASH"),
        (lambda op, current: op.model_copy(update={"before": "not current"}), "BEFORE_MISMATCH"),
        (
            lambda op, current: op.model_copy(
                update={"after": op.after.replace("id: concept_topic", "id: concept_changed")}
            ),
            "PAGE_ID_CHANGED",
        ),
        (
            lambda op, current: op.model_copy(
                update={"after": op.after.replace("page_type: concept", "page_type: alien")}
            ),
            "PAGE_TYPE_INVALID",
        ),
        (
            lambda op, current: op.model_copy(
                update={"after": op.after + "\n[[wiki/concepts/missing.md]]\n"}
            ),
            "BROKEN_WIKILINK",
        ),
    ],
)
def test_validator_reports_page_and_link_failures(validator_setup, mutation, expected_code):
    validator, changeset, current, _ = validator_setup
    operation = mutation(changeset.operations[0], current)

    result = validator.validate(changeset.model_copy(update={"operations": [operation]}))

    assert expected_code in {issue.code for issue in result.issues}


def test_validator_rejects_unknown_source_and_out_of_range_time(validator_setup):
    validator, changeset, _, source = validator_setup
    unknown = Citation(source_id="src_20260618_deadbeef", start_ms=0, end_ms=1000)
    beyond = Citation(source_id=source.source_id, start_ms=4000, end_ms=5001)
    operation = changeset.operations[0].model_copy(update={"citations": [unknown, beyond]})

    result = validator.validate(changeset.model_copy(update={"operations": [operation]}))
    codes = {issue.code for issue in result.issues}

    assert "SOURCE_UNKNOWN" in codes
    assert "CITATION_OUT_OF_RANGE" in codes
    assert result.valid is False


def test_validator_rejects_create_path_that_exists(validator_setup):
    validator, changeset, _, _ = validator_setup
    operation = changeset.operations[0].model_copy(
        update={"action": "create", "base_hash": None, "before": None}
    )

    result = validator.validate(changeset.model_copy(update={"operations": [operation]}))

    assert "CREATE_PATH_EXISTS" in {issue.code for issue in result.issues}


def test_key_fact_without_citation_is_warning(validator_setup):
    validator, changeset, _, _ = validator_setup
    operation = changeset.operations[0].model_copy(update={"citations": []})

    result = validator.validate(changeset.model_copy(update={"operations": [operation]}))

    issue = next(issue for issue in result.issues if issue.code == "KEY_CLAIM_WITHOUT_CITATION")
    assert issue.severity == "warning"
    assert result.valid is True


def test_all_validator_issues_have_code_message_and_severity(validator_setup):
    validator, changeset, _, _ = validator_setup
    operation = changeset.operations[0].model_copy(update={"base_hash": "stale", "citations": []})

    issues = validator.validate(changeset.model_copy(update={"operations": [operation]})).issues

    assert all(issue.code and issue.message for issue in issues)
    assert all(issue.severity in {"error", "warning"} for issue in issues)
