from datetime import UTC, datetime

import pytest
from vid2note_core.source.registrar import SourceRegistrar, SourceRegistration
from vid2note_core.vault.layout import VaultLayout


@pytest.fixture
def layout(tmp_path):
    return VaultLayout.initialize(tmp_path / "vault")


@pytest.fixture
def registration(tmp_path):
    srt = tmp_path / "transcript.srt"
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:03,500\nEvidence statement.\n",
        encoding="utf-8",
    )
    note = tmp_path / "note.md"
    note.write_text("# Model summary\n\nInferred explanation.\n", encoding="utf-8")
    return SourceRegistration(
        task_id="task_0123456789ab",
        canonical_url="https://example.com/watch?v=1&utm_source=test",
        title="Evidence Lesson",
        imported_at=datetime(2026, 6, 18, tzinfo=UTC),
        srt_path=srt,
        note_path=note,
    )


def test_register_source_writes_raw_and_source_note(layout, registration):
    registrar = SourceRegistrar(layout)

    record = registrar.register(registration)

    raw = layout.raw / record.source_id
    assert (raw / "source.yaml").exists()
    assert (raw / "transcript.srt").exists()
    assert (raw / "transcript.md").exists()
    notes = list(layout.sources.glob(f"{record.source_id}--*.md"))
    assert len(notes) == 1
    source_note = notes[0].read_text()
    assert "## 综合/推断" in source_note
    assert f"vid2note://source/{record.source_id}?start=1000&end=3500" in source_note


def test_duplicate_source_reuses_raw_record(layout, registration):
    registrar = SourceRegistrar(layout)
    first = registrar.register(registration)
    second = registrar.register(registration)

    assert second.source_id == first.source_id
    assert len(list(layout.raw.glob("*/source.yaml"))) == 1


def test_registration_failure_leaves_no_partial_source(layout, registration):
    registration.note_path.unlink()

    with pytest.raises(FileNotFoundError):
        SourceRegistrar(layout).register(registration)

    assert not list(layout.raw.glob("*/source.yaml"))
    assert not list(layout.sources.glob("src_*.md"))
