"""处理 API 集成测试

覆盖：start 创建任务、status 实时查询（pending/running/completed）、
404 不存在、非法 task_id、result 产物查询（未完成/已完成含产物）。
"""

import pytest

from vid2note_core.storage.artifact_store import ArtifactStore
from vid2note_core.storage.task_repo import TaskRepository
from vid2note_core.types import NodeName, TaskStatus
from vid2note_core.utils.security import validate_file_id


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    """把 ArtifactStore 默认目录指到 tmp_path，隔离产物落盘。"""
    target = tmp_path / "tasks"
    monkeypatch.setattr(
        ArtifactStore,
        "__init__",
        lambda self, base_dir=None: (
            object.__setattr__(self, "base_dir", target)
            and target.mkdir(parents=True, exist_ok=True)
        ),
    )
    return ArtifactStore()


def test_start_creates_pending_task(client):
    resp = client.post(
        "/api/v1/process/start",
        json={"video_url": "https://youtube.com/x"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # task_id 是合法格式（注意：process 返回 task_id，与 file_id 不同，用 TaskId 校验）
    from vid2note_core.types import TaskId

    assert TaskId.is_valid(data["task_id"])
    assert data["status"] == "pending"

    # 任务确实入库且为 pending
    repo = TaskRepository()
    task = repo.get_by_id(data["task_id"])
    assert task is not None
    assert task.status == TaskStatus.PENDING
    assert task.video_url == "https://youtube.com/x"


def test_start_requires_input(client):
    """无任何输入参数返回 400"""
    resp = client.post("/api/v1/process/start", json={})
    assert resp.status_code == 400


def test_start_with_srt_file(client):
    resp = client.post(
        "/api/v1/process/start",
        json={"srt_file": "file_abcdef012345"},
    )
    assert resp.status_code == 200
    repo = TaskRepository()
    task = repo.get_by_id(resp.json()["task_id"])
    assert task.srt_file == "file_abcdef012345"


def test_status_pending(client):
    """start 后立即查 status 应为 pending"""
    start = client.post("/api/v1/process/start", json={"video_url": "https://x.com/v"})
    task_id = start.json()["task_id"]
    resp = client.get(f"/api/v1/process/status/{task_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == task_id
    assert data["status"] == "pending"
    assert data["progress"] == 0


def test_status_reflects_running(client):
    """手动把任务更新为 running 后，status 反映真实状态"""
    start = client.post("/api/v1/process/start", json={"video_url": "https://x.com/v"})
    task_id = start.json()["task_id"]
    repo = TaskRepository()
    repo.update(task_id, status=TaskStatus.RUNNING, progress=50, current_step="transcribe")

    resp = client.get(f"/api/v1/process/status/{task_id}")
    data = resp.json()
    assert data["status"] == "running"
    assert data["progress"] == 50
    assert data["current_step"] == "transcribe"


def test_status_not_found(client):
    resp = client.get("/api/v1/process/status/task_000000000000")
    assert resp.status_code == 404


def test_status_invalid_task_id(client):
    """非法 task_id 格式返回 400"""
    resp = client.get("/api/v1/process/status/not-a-valid-id")
    assert resp.status_code == 400


def test_result_not_completed(client, isolated_store):
    """任务未完成时 result 仅返回状态，无 artifacts"""
    start = client.post("/api/v1/process/start", json={"video_url": "https://x.com/v"})
    task_id = start.json()["task_id"]
    resp = client.get(f"/api/v1/process/result/{task_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert "artifacts" not in data


def test_result_completed_with_artifacts(client, isolated_store):
    """任务完成后 result 返回产物文本"""
    start = client.post("/api/v1/process/start", json={"video_url": "https://x.com/v"})
    task_id = start.json()["task_id"]

    # 写入产物 + 标记完成
    store = ArtifactStore()
    store.write_artifact(
        task_id, NodeName.ORGANIZE.value, "markdown_file", "# 笔记".encode("utf-8")
    )
    store.write_artifact(task_id, NodeName.MINDMAP.value, "mindmap_file", "mindmap".encode("utf-8"))
    repo = TaskRepository()
    repo.update(task_id, status=TaskStatus.COMPLETED, progress=100)

    resp = client.get(f"/api/v1/process/result/{task_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["progress"] == 100
    assert "artifacts" in data
    assert data["artifacts"]["markdown"] == "# 笔记"
    assert data["artifacts"]["mindmap"] == "mindmap"


def test_result_invalid_task_id(client):
    resp = client.get("/api/v1/process/result/bad-id")
    assert resp.status_code == 400


def test_result_not_found(client):
    resp = client.get("/api/v1/process/result/task_000000000000")
    assert resp.status_code == 404
