"""
Tasks API integration tests
"""

import pytest
from fastapi.testclient import TestClient
from vid2note_server.main import app
from vid2note_core.storage.artifact_store import ArtifactStore
from vid2note_core.storage.db import Database
from vid2note_core.storage.task_repo import TaskRepository
from vid2note_core.types import TaskStatus


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_db():
    Database.reset_instance()
    yield


def test_create_task():
    response = client.post("/api/v1/tasks", json={"video_url": "https://example.com/video"})
    assert response.status_code == 200
    data = response.json()
    assert data["task_id"].startswith("task_")
    assert data["status"] == "pending"


def test_list_tasks():
    client.post("/api/v1/tasks", json={"video_url": "https://example.com/video1"})
    client.post("/api/v1/tasks", json={"video_url": "https://example.com/video2"})
    response = client.get("/api/v1/tasks")
    assert response.status_code == 200
    data = response.json()
    assert len(data["tasks"]) == 2


def test_get_task():
    r = client.post("/api/v1/tasks", json={"video_url": "https://example.com/video"})
    task_id = r.json()["task_id"]
    response = client.get(f"/api/v1/tasks/{task_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == task_id


def test_get_task_not_found():
    response = client.get("/api/v1/tasks/task_nonexistent123")
    assert response.status_code == 404


# ── rerun ────────────────────────────────────────────────


def test_rerun_resets_status_and_progress():
    """rerun 后任务应回到 pending、progress=0。"""
    r = client.post("/api/v1/tasks", json={"video_url": "https://example.com/v"})
    task_id = r.json()["task_id"]
    # 先标记 completed + progress 100
    TaskRepository().update(task_id, status=TaskStatus.COMPLETED, progress=100)

    resp = client.post(f"/api/v1/tasks/{task_id}/rerun")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"

    task = TaskRepository().get_by_id(task_id)
    assert task.status == TaskStatus.PENDING
    assert task.progress == 0


def test_rerun_unknown_task_returns_404():
    resp = client.post("/api/v1/tasks/task_000000000000/rerun")
    assert resp.status_code == 404


def test_rerun_invalid_id_returns_404():
    resp = client.post("/api/v1/tasks/not-a-valid-id/rerun")
    assert resp.status_code == 404


def test_rerun_from_node_deletes_downstream():
    """rerun from_node=transcribe 应删除 transcribe 及其下游产物，保留 download。"""
    r = client.post("/api/v1/tasks", json={"video_url": "https://example.com/v"})
    task_id = r.json()["task_id"]

    store = ArtifactStore()
    store.write_artifact(task_id, "download", "video_file", b"vid")
    store.write_artifact(task_id, "transcribe", "srt_file", b"srt")
    store.write_artifact(task_id, "organize", "markdown_file", b"md")
    store.write_artifact(task_id, "mindmap", "mindmap_file", b"mm")

    client.post(f"/api/v1/tasks/{task_id}/rerun", json={"from_node": "transcribe"})

    # download（from_node 之前）保留；transcribe 及下游被删除（需重跑）
    assert store.exists(task_id, "download", "video_file")
    assert not store.exists(task_id, "transcribe", "srt_file")
    assert not store.exists(task_id, "organize", "markdown_file")
    assert not store.exists(task_id, "mindmap", "mindmap_file")

