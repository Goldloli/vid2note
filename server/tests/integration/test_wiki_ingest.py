import io
import time

from vid2note_core.types import TaskStatus


def test_srt_ingest_proposes_and_approval_compiles_formal_wiki(client):
    upload = client.post(
        "/api/v1/upload/srt",
        files={
            "file": (
                "wiki-evidence.srt",
                io.BytesIO(b"1\n00:00:01,000 --> 00:00:03,000\nWiki evidence.\n"),
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
    pending = client.get("/api/v1/changesets", params={"status": "pending"}).json()
    assert len(pending) == 1
    approved = client.post(f"/api/v1/changesets/{pending[0]['id']}/approve", json={})
    assert approved.status_code == 200
    operation = approved.json()["operations"][0]
    page = client.get("/api/v1/vault/page", params={"path": operation["path"]}).json()
    assert "vid2note://source/" in page["content"]
    assert f"[[{operation['path']}|" in client.app.state.services.vault_layout.index.read_text()
    assert pending[0]["id"] in client.app.state.services.vault_layout.log.read_text()
