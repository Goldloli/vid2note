"""全链路端到端集成测试

upload SRT → process/start → process/status → process/result

验证三个 API 端点的完整链路协同工作：
  1. POST /upload/srt 上传字幕文件，得到真实 file_id
  2. POST /process/start 用 file_id 启动处理，得到 task_id
  3. GET  /process/status/{task_id} 查询实时状态
  4. GET  /process/result/{task_id} 查询产物（未完成时仅状态）

数据隔离：UploadStore 和 ArtifactStore 通过 monkeypatch 指到 tmp_path。
"""
import io
from pathlib import Path

import pytest

from vid2note_core.storage.artifact_store import ArtifactStore
from vid2note_core.storage.task_repo import TaskRepository
from vid2note_core.storage.upload_store import UploadStore
from vid2note_core.types import NodeName, TaskStatus
from vid2note_core.utils.security import validate_file_id


SAMPLE_SRT = """1
00:00:00,000 --> 00:00:02,000
这是第一句字幕。

2
00:00:02,500 --> 00:00:05,000
这是第二句字幕，用于全链路测试。
"""


@pytest.fixture
def isolated_stores(tmp_path, monkeypatch):
    """隔离 UploadStore + ArtifactStore 到 tmp_path。"""
    upload_dir = tmp_path / "uploads"
    artifact_dir = tmp_path / "tasks"

    def _upload_init(self, base_dir=None):
        object.__setattr__(self, "base_dir", upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)

    def _artifact_init(self, base_dir=None):
        object.__setattr__(self, "base_dir", artifact_dir)
        artifact_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(UploadStore, "__init__", _upload_init)
    monkeypatch.setattr(ArtifactStore, "__init__", _artifact_init)
    return tmp_path


def test_full_chain_upload_start_status_result(client, isolated_stores):
    """全链路：上传 → 启动 → 状态 → 产物"""
    # ── Step 1: 上传 SRT ──────────────────────────────
    upload_resp = client.post(
        "/api/v1/upload/srt",
        files={"file": ("test.srt", io.BytesIO(SAMPLE_SRT.encode("utf-8")), "text/plain")},
    )
    assert upload_resp.status_code == 200
    upload_data = upload_resp.json()
    assert validate_file_id(upload_data["file_id"])
    file_id = upload_data["file_id"]
    assert upload_data["filename"] == "test.srt"

    # 验证文件确实落盘
    store = UploadStore()
    assert store.exists(file_id)

    # ── Step 2: 启动处理（用上传的 file_id）─────────
    start_resp = client.post(
        "/api/v1/process/start",
        json={"srt_file": file_id, "llm_provider": "mock", "asr_provider": "asrtools-b"},
    )
    assert start_resp.status_code == 200
    task_id = start_resp.json()["task_id"]
    assert start_resp.json()["status"] == "pending"

    # 任务入库
    repo = TaskRepository()
    task = repo.get_by_id(task_id)
    assert task is not None
    assert task.status == TaskStatus.PENDING
    assert task.srt_file == file_id

    # ── Step 3: 查询状态（pending）────────────────────
    status_resp = client.get(f"/api/v1/process/status/{task_id}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["task_id"] == task_id
    assert status_data["status"] == "pending"
    assert status_data["progress"] == 0

    # 模拟任务推进到 running
    repo.update(task_id, status=TaskStatus.RUNNING, progress=50, current_step="transcribe")
    status_resp = client.get(f"/api/v1/process/status/{task_id}")
    assert status_resp.json()["status"] == "running"
    assert status_resp.json()["progress"] == 50
    assert status_resp.json()["current_step"] == "transcribe"

    # ── Step 4: 产物查询（未完成时仅状态）────────────
    result_resp = client.get(f"/api/v1/process/result/{task_id}")
    assert result_resp.status_code == 200
    result_data = result_resp.json()
    assert result_data["status"] == "running"
    assert "artifacts" not in result_data

    # ── Step 5: 完成后产物查询 ────────────────────────
    astore = ArtifactStore()
    astore.write_artifact(
        task_id, NodeName.ORGANIZE.value, "markdown_file", "# 全链路测试笔记".encode("utf-8")
    )
    astore.write_artifact(
        task_id, NodeName.MINDMAP.value, "mindmap_file", "mindmap".encode("utf-8")
    )
    repo.update(task_id, status=TaskStatus.COMPLETED, progress=100)

    result_resp = client.get(f"/api/v1/process/result/{task_id}")
    result_data = result_resp.json()
    assert result_data["status"] == "completed"
    assert result_data["progress"] == 100
    assert "artifacts" in result_data
    assert result_data["artifacts"]["markdown"] == "# 全链路测试笔记"
    assert result_data["artifacts"]["mindmap"] == "mindmap"


def test_full_chain_invalid_file_id_rejected(client, isolated_stores):
    """用不存在的 file_id 启动应仍创建任务（file_id 校验在执行阶段）"""
    start_resp = client.post(
        "/api/v1/process/start",
        json={"srt_file": "file_000000000000"},
    )
    assert start_resp.status_code == 200
    # 任务创建成功（pending），实际执行时才处理 file 不存在
    assert start_resp.json()["status"] == "pending"


def test_full_chain_status_not_found(client, isolated_stores):
    """查询不存在的任务返回 404"""
    resp = client.get("/api/v1/process/status/task_000000000000")
    assert resp.status_code == 404


def test_full_chain_result_not_found(client, isolated_stores):
    """查询不存在任务的产物返回 404"""
    resp = client.get("/api/v1/process/result/task_000000000000")
    assert resp.status_code == 404
