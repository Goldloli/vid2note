import json
from datetime import UTC, datetime

import pytest
from vid2note_core.source.models import SourceRecord
from vid2note_core.vault.models import VaultPage
from vid2note_core.vault.repository import content_hash
from vid2note_core.wiki.compiler import (
    CompileInput,
    WikiCompiler,
    WikiInvalidChangeSetError,
)


class FakeLLM:
    def __init__(self, *responses: str):
        self.responses = list(responses)
        self.messages: list[list[dict[str, str]]] = []

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        self.messages.append(messages)
        return self.responses.pop(0)


def _page(path: str, content: str) -> VaultPage:
    return VaultPage(
        path=path,
        content=content,
        content_hash=content_hash(content),
        modified_at=datetime(2026, 6, 19, tzinfo=UTC),
    )


@pytest.fixture
def compile_input():
    return CompileInput(
        source=SourceRecord(
            source_id="src_20260618_01234567",
            canonical_url="https://example.com/2",
            content_sha256="a" * 64,
            title="Second source",
            duration_ms=10_000,
            imported_at=datetime(2026, 6, 18, tzinfo=UTC),
            original_available=False,
            original_relative_path=None,
        ),
        source_note=_page("sources/source.md", "# Source\n\nNew evidence."),
        schema_text="Allowed type: concept",
        index_text="POC Trap",
        related_pages=[_page("wiki/concepts/ai-delivery.md", "# AI Delivery\n\nOld claim.")],
    )


def _response(classification: str, *, contradiction: bool = False) -> str:
    if classification == "duplicate":
        return json.dumps({"classification": "duplicate", "changeset": None})
    after = "# AI Delivery\n\nNew claim."
    contradictions = []
    if contradiction:
        after = "# AI Delivery\n\n## 观点 A\nOld.\n\n## 观点 B\nNew."
        citation = {
            "source_id": "src_20260618_01234567",
            "start_ms": 1000,
            "end_ms": 3000,
        }
        contradictions = [
            {
                "topic": "Delivery",
                "claim_a": "Old",
                "claim_b": "New",
                "citations_a": [citation],
                "citations_b": [citation],
            }
        ]
    return json.dumps(
        {
            "classification": classification,
            "changeset": {
                "id": "chg_0123456789ab",
                "created_at": "2026-06-19T00:00:00Z",
                "source_ids": ["src_20260618_01234567"],
                "base_revision": "rev-1",
                "agent_runtime": "built-in",
                "summary": "Update existing page",
                "operations": [
                    {
                        "page_id": "concept_ai_delivery",
                        "path": "wiki/concepts/ai-delivery.md",
                        "base_hash": "base",
                        "action": "update",
                        "before": "# AI Delivery\n\nOld claim.",
                        "after": after,
                        "rationale": "Second source",
                        "citations": [
                            {
                                "source_id": "src_20260618_01234567",
                                "start_ms": 1000,
                                "end_ms": 3000,
                            }
                        ],
                    }
                ],
                "contradictions": contradictions,
            },
        }
    )


def test_second_source_updates_existing_page(compile_input):
    compiler = WikiCompiler(FakeLLM(_response("enhancement")))

    result = compiler.propose(compile_input)

    assert result.changeset is not None
    assert result.changeset.operations[0].action == "update"
    assert result.changeset.operations[0].page_id == "concept_ai_delivery"


def test_duplicate_claim_does_not_append_duplicate_paragraph(compile_input):
    result = WikiCompiler(FakeLLM(_response("duplicate"))).propose(compile_input)

    assert result.changeset is None
    assert result.classification == "duplicate"


def test_conflicting_claims_are_preserved_as_contradiction(compile_input):
    result = WikiCompiler(FakeLLM(_response("contradiction", contradiction=True))).propose(
        compile_input
    )

    assert result.changeset is not None
    assert len(result.changeset.contradictions) == 1
    assert "观点 A" in result.changeset.operations[0].after
    assert "观点 B" in result.changeset.operations[0].after


def test_invalid_json_is_repaired_once(compile_input):
    llm = FakeLLM("not json", _response("enhancement"))

    result = WikiCompiler(llm).propose(compile_input)

    assert result.classification == "enhancement"
    assert len(llm.messages) == 2
    assert "validation" in llm.messages[1][-1]["content"].lower()


def test_twice_invalid_output_raises_typed_error(compile_input):
    compiler = WikiCompiler(FakeLLM("not json", "still not json"))

    with pytest.raises(WikiInvalidChangeSetError) as error:
        compiler.propose(compile_input)

    assert error.value.code == "WIKI_INVALID_CHANGESET"
