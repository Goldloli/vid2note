import io
import time

from vid2note_core.types import TaskStatus


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
