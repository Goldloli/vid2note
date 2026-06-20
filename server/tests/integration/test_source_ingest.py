import io
import time

from vid2note_core.types import TaskStatus


def _source_payload():
    return {
        "canonical_url": "https://example.com/watch?v=duplicate&utm_source=test",
        "title": "Duplicate source",
        "srt_content": "1\n00:00:01,000 --> 00:00:03,000\nEvidence.\n",
        "note_content": "# Summary\n\nEvidence summary.\n",
    }


def test_sources_ingest_returns_existing_source_for_duplicate(client):
    payload = _source_payload()

    first = client.post("/api/v1/sources/ingest", json=payload)
    second = client.post("/api/v1/sources/ingest", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["source_id"] == first.json()["source_id"]
    loaded = client.get(f"/api/v1/sources/{first.json()['source_id']}")
    assert loaded.status_code == 200
    assert loaded.json()["canonical_url"] == "https://example.com/watch?v=duplicate"


def test_completed_srt_task_is_registered_in_vault(client):
    upload = client.post(
        "/api/v1/upload/srt",
        files={
            "file": (
                "evidence.srt",
                io.BytesIO(b"1\n00:00:01,000 --> 00:00:03,000\nEvidence.\n"),
                "text/plain",
            )
        },
    ).json()
    task_id = client.post(
        "/api/v1/process/start",
        json={"srt_file": upload["file_id"], "llm_provider": "mock"},
    ).json()["task_id"]

    deadline = time.monotonic() + 5
    task = client.app.state.services.tasks.get_by_id(task_id)
    while time.monotonic() < deadline and task.status not in {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
    }:
        time.sleep(0.05)
        task = client.app.state.services.tasks.get_by_id(task_id)

    assert task.status is TaskStatus.COMPLETED, task.error_message
    layout = client.app.state.services.vault_layout
    source_notes = list(layout.sources.glob("src_*.md"))
    assert len(source_notes) == 1
    assert "vid2note://source/" in source_notes[0].read_text()
