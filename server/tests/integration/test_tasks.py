"""
Tasks API integration tests
"""

import pytest
from fastapi.testclient import TestClient
from vid2note_server.main import app
from vid2note_core.storage.db import Database


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
