import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from vid2note_core.source.models import SourceRecord
from vid2note_core.source.registrar import SourceRegistrar, SourceRegistration
from vid2note_core.vault.layout import VaultLayout
from vid2note_core.vault.models import VaultPage
from vid2note_core.vault.repository import VaultRepository, content_hash
from vid2note_core.wiki.applier import ChangeSetApplier
from vid2note_core.wiki.compiler import CompileInput, WikiCompiler
from vid2note_core.wiki.index import parse_index
from vid2note_core.wiki.models import ChangeOperation, ChangeSet, Citation
from vid2note_core.wiki.store import ChangeSetStore
from vid2note_core.wiki.validator import ChangeSetValidator

FIXTURES = Path(__file__).parent / "fixtures"


class FakeLLM:
    def __init__(self, response: dict):
        self.response = response

    def chat(self, messages, **kwargs):
        return json.dumps(self.response, ensure_ascii=False)


def _fixture(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _source(source_id="src_20260618_01234567") -> SourceRecord:
    return SourceRecord(
        source_id=source_id,
        canonical_url="https://example.com/source",
        content_sha256="a" * 64,
        title="Scenario source",
        duration_ms=5000,
        imported_at=datetime(2026, 6, 18, tzinfo=UTC),
        original_available=False,
        original_relative_path=None,
    )


def _page(path: str, content: str) -> VaultPage:
    return VaultPage(
        path=path,
        content=content,
        content_hash=content_hash(content),
        modified_at=datetime(2026, 6, 19, tzinfo=UTC),
    )


def _response(fixture: dict) -> dict:
    if fixture["classification"] == "duplicate":
        return {"classification": "duplicate", "changeset": None}
    citation = {
        "source_id": "src_20260618_01234567",
        "start_ms": 1000,
        "end_ms": 5000,
    }
    contradictions = []
    if fixture.get("contradiction"):
        contradictions = [
            {
                "topic": "Scenario",
                "claim_a": "View A",
                "claim_b": "View B",
                "citations_a": [citation],
                "citations_b": [citation],
            }
        ]
    return {
        "classification": fixture["classification"],
        "changeset": {
            "id": "chg_0123456789ab",
            "created_at": "2026-06-19T00:00:00Z",
            "source_ids": [citation["source_id"]],
            "base_revision": "scenario",
            "agent_runtime": "fake",
            "summary": fixture["name"],
            "operations": [
                {
                    "page_id": "concept_compounding",
                    "path": "wiki/concepts/compounding.md",
                    "base_hash": "stale" if fixture.get("stale_base") else None,
                    "action": fixture["action"],
                    "before": fixture.get("before_claim"),
                    "after": fixture["after_claim"],
                    "rationale": fixture["name"],
                    "citations": [citation],
                }
            ],
            "contradictions": contradictions,
        },
    }


@pytest.mark.parametrize("fixture_path", sorted(FIXTURES.glob("*.yaml")), ids=lambda p: p.stem)
def test_compiler_scenario_classification_and_shape(fixture_path):
    fixture = _fixture(fixture_path)
    result = WikiCompiler(FakeLLM(_response(fixture))).propose(
        CompileInput(
            source=_source(),
            source_note=_page("sources/source.md", "# Source"),
            schema_text="concept",
            index_text="index",
            related_pages=[],
        )
    )

    assert result.classification == fixture["classification"]
    if fixture["action"] is None:
        assert result.changeset is None
    else:
        assert result.changeset.operations[0].action == fixture["action"]
        if fixture.get("contradiction"):
            assert len(result.changeset.contradictions) == 1
            assert "观点 A" in result.changeset.operations[0].after
            assert "观点 B" in result.changeset.operations[0].after


def _register(layout: VaultLayout, tmp_path: Path, name: str, text: str):
    srt = tmp_path / f"{name}.srt"
    srt.write_text(f"1\n00:00:01,000 --> 00:00:05,000\n{text}\n", encoding="utf-8")
    note = tmp_path / f"{name}.md"
    note.write_text(f"# {name}\n", encoding="utf-8")
    return SourceRegistrar(layout).register(
        SourceRegistration(
            task_id=f"task_{'a' * 11}{name[-1]}",
            canonical_url=f"https://example.com/{name}",
            title=name,
            imported_at=datetime(2026, 6, 18, tzinfo=UTC),
            srt_path=srt,
            note_path=note,
            duration_ms=5000,
        )
    )


def _formal_page(source_ids: list[str], claim: str) -> str:
    sources = "\n".join(f"  - {source_id}" for source_id in source_ids)
    return (
        "---\nid: concept_compounding\ntitle: Compounding\npage_type: concept\n"
        f"status: active\nsources:\n{sources}\n"
        "created_at: 2026-06-18\nupdated_at: 2026-06-19\n---\n\n"
        f"# Compounding\n\n{claim}\n"
    )


def test_two_sources_compound_the_same_page_and_index_count(tmp_path):
    layout = VaultLayout.initialize(tmp_path / "vault")
    source_a = _register(layout, tmp_path, "source-a", "Initial claim")
    source_b = _register(layout, tmp_path, "source-b", "Enhanced claim")
    repository = VaultRepository(layout)
    store = ChangeSetStore(layout.root)
    validator = ChangeSetValidator(layout, repository)
    applier = ChangeSetApplier(layout, repository, store, validator)
    first_content = _formal_page(
        [source_a.source_id],
        f"Initial claim [evidence](vid2note://source/{source_a.source_id}?start=1000&end=5000)",
    )
    first = ChangeSet(
        id="chg_aaaaaaaaaaaa",
        created_at=datetime(2026, 6, 19, tzinfo=UTC),
        source_ids=[source_a.source_id],
        base_revision="initial",
        agent_runtime="fake",
        summary="Create compounding page",
        operations=[
            ChangeOperation(
                page_id="concept_compounding",
                path="wiki/concepts/compounding.md",
                action="create",
                after=first_content,
                rationale="Initial source",
                citations=[Citation(source_id=source_a.source_id, start_ms=1000, end_ms=5000)],
            )
        ],
        contradictions=[],
    )
    store.save_pending(first)
    applier.apply(first)
    current = repository.read_page("wiki/concepts/compounding.md")
    second_content = _formal_page(
        [source_a.source_id, source_b.source_id],
        current.content.split("# Compounding\n\n", 1)[1].strip()
        + f"\n\nEnhanced claim [evidence](vid2note://source/{source_b.source_id}?start=1000&end=5000)",
    )
    second = ChangeSet(
        id="chg_bbbbbbbbbbbb",
        created_at=datetime(2026, 6, 19, tzinfo=UTC),
        source_ids=[source_b.source_id],
        base_revision=first.id,
        agent_runtime="fake",
        summary="Enhance compounding page",
        operations=[
            ChangeOperation(
                page_id="concept_compounding",
                path=current.path,
                base_hash=current.content_hash,
                action="update",
                before=current.content,
                after=second_content,
                rationale="Second related source",
                citations=[Citation(source_id=source_b.source_id, start_ms=1000, end_ms=5000)],
            )
        ],
        contradictions=[],
    )
    store.save_pending(second)
    applier.apply(second)

    final = repository.read_page("wiki/concepts/compounding.md").content
    entry = next(
        item
        for item in parse_index(layout.index.read_text())
        if item.path.endswith("compounding.md")
    )
    assert "Initial claim" in final and "Enhanced claim" in final
    assert entry.source_count == 2
    assert len(list(layout.wiki.glob("**/compounding.md"))) == 1


def test_stale_base_scenario_is_rejected_before_apply(tmp_path):
    layout = VaultLayout.initialize(tmp_path / "vault")
    source = _register(layout, tmp_path, "source-a", "Initial claim")
    repository = VaultRepository(layout)
    existing = _formal_page([source.source_id], "Initial claim")
    layout.wiki.joinpath("concepts", "compounding.md").write_text(existing, encoding="utf-8")
    fixture = _fixture(FIXTURES / "06-reject-stale-base-hash.yaml")
    changeset = (
        WikiCompiler(FakeLLM(_response(fixture)))
        .propose(
            CompileInput(
                source=source,
                source_note=_page("sources/source.md", "# Source"),
                schema_text="concept",
                index_text="index",
                related_pages=[repository.read_page("wiki/concepts/compounding.md")],
            )
        )
        .changeset
    )

    result = ChangeSetValidator(layout, repository).validate(changeset)

    assert not result.valid
    assert "STALE_BASE_HASH" in {issue.code for issue in result.issues}
