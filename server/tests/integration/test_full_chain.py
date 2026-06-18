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
import time

from vid2note_core.types import TaskStatus
from vid2note_core.utils.security import validate_file_id

SAMPLE_SRT = """1
00:00:00,000 --> 00:00:02,000
这是第一句字幕。

2
00:00:02,500 --> 00:00:05,000
这是第二句字幕，用于全链路测试。
"""


def test_full_chain_upload_start_status_result(client):
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
    store = client.app.state.services.uploads
    assert store.exists(file_id)

    # ── Step 2: 启动处理（用上传的 file_id）─────────
    start_resp = client.post(
        "/api/v1/process/start",
        json={"srt_file": file_id, "llm_provider": "mock", "asr_provider": "funasr"},
    )
    assert start_resp.status_code == 200
    task_id = start_resp.json()["task_id"]
    assert start_resp.json()["status"] == "pending"

    # 任务入库
    repo = client.app.state.services.tasks
    task = repo.get_by_id(task_id)
    assert task is not None
    assert task.status == TaskStatus.PENDING
    assert task.srt_file == file_id

    # ── Step 3: 等待真实 Worker 完成 ──────────────────
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        task = repo.get_by_id(task_id)
        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            break
        time.sleep(0.05)
    assert task.status is TaskStatus.COMPLETED, task.error_message

    # ── Step 4: 从真实 ArtifactStore 查询产物 ─────────
    result_resp = client.get(f"/api/v1/process/result/{task_id}")
    result_data = result_resp.json()
    assert result_data["status"] == "completed"
    assert result_data["progress"] == 100
    assert "artifacts" in result_data
    assert "# 来源笔记" in result_data["artifacts"]["markdown"]
    assert "证据：00:00:00–00:00:02" in result_data["artifacts"]["markdown"]
    assert "这是第一句字幕" in result_data["artifacts"]["srt"]
    assert result_data["artifacts"]["mindmap"]

    rerun_resp = client.post(f"/api/v1/tasks/{task_id}/rerun", json={"from_node": "organize"})
    assert rerun_resp.status_code == 200
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        task = repo.get_by_id(task_id)
        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            break
        time.sleep(0.05)
    assert task.status is TaskStatus.COMPLETED, task.error_message


def test_full_chain_invalid_file_id_rejected(client):
    """用不存在的 file_id 启动应仍创建任务（file_id 校验在执行阶段）"""
    start_resp = client.post(
        "/api/v1/process/start",
        json={"srt_file": "file_000000000000"},
    )
    assert start_resp.status_code == 200
    # 任务创建成功（pending），实际执行时才处理 file 不存在
    assert start_resp.json()["status"] == "pending"


def test_full_chain_status_not_found(client):
    """查询不存在的任务返回 404"""
    resp = client.get("/api/v1/process/status/task_000000000000")
    assert resp.status_code == 404


def test_full_chain_result_not_found(client):
    """查询不存在任务的产物返回 404"""
    resp = client.get("/api/v1/process/result/task_000000000000")
    assert resp.status_code == 404
