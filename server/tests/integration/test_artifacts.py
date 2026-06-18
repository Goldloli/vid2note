"""产物下载/导出 API 集成测试"""

import zipfile
from io import BytesIO

from vid2note_core.storage.artifact_store import ArtifactStore
from vid2note_core.storage.db import Database
from vid2note_core.storage.task_repo import TaskRepository
from vid2note_core.types import TaskId, TaskStatus


def _make_task(client):
    """创建一个任务并返回 task_id。"""
    r = client.post("/api/v1/tasks", json={"video_url": "https://example.com/v"})
    return r.json()["task_id"]


def test_list_artifacts(client):
    """列出产物应返回文件名、类型、大小。"""
    task_id = _make_task(client)
    store = ArtifactStore()
    payload = "# 笔记\n正文".encode("utf-8")
    store.write_artifact(task_id, "organize", "markdown_file", payload)

    resp = client.get(f"/api/v1/tasks/{task_id}/artifacts")
    assert resp.status_code == 200
    data = resp.json()
    names = [a["name"] for a in data["artifacts"]]
    assert "note.md" in names
    md = next(a for a in data["artifacts"] if a["name"] == "note.md")
    assert md["type"] == "markdown"
    assert md["size"] == len(payload)


def test_list_artifacts_unknown_task_404(client):
    resp = client.get("/api/v1/tasks/task_000000000000/artifacts")
    assert resp.status_code == 404


def test_list_artifacts_invalid_id_404(client):
    resp = client.get("/api/v1/tasks/not-a-task/artifacts")
    assert resp.status_code == 404


def test_download_artifact(client):
    """下载 markdown 产物应返回正确内容和 Content-Type。"""
    task_id = _make_task(client)
    content = "# 标题\n\n正文内容".encode("utf-8")
    ArtifactStore().write_artifact(task_id, "organize", "markdown_file", content)

    resp = client.get(f"/api/v1/tasks/{task_id}/artifacts/organize_markdown_file")
    assert resp.status_code == 200
    assert resp.content == content
    assert "text/markdown" in resp.headers["content-type"]
    assert 'attachment; filename="note.md"' in resp.headers["content-disposition"]


def test_download_artifact_not_found(client):
    """产物不存在时应 404。"""
    task_id = _make_task(client)
    resp = client.get(f"/api/v1/tasks/{task_id}/artifacts/nonexistent_file")
    assert resp.status_code == 404


def test_download_artifact_srt(client):
    """下载 srt 产物。"""
    task_id = _make_task(client)
    ArtifactStore().write_artifact(
        task_id, "transcribe", "srt_file", b"1\n00:00:00,000 --> 00:00:01,000\nhi\n"
    )
    resp = client.get(f"/api/v1/tasks/{task_id}/artifacts/transcribe_srt_file")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/x-subrip"


def test_export_all_zip(client):
    """导出 zip 应包含所有产物。"""
    task_id = _make_task(client)
    store = ArtifactStore()
    store.write_artifact(task_id, "organize", "markdown_file", b"# md")
    store.write_artifact(task_id, "transcribe", "srt_file", b"srt content")
    store.write_artifact(task_id, "mindmap", "mindmap_file", b"mindmap")

    resp = client.get(f"/api/v1/tasks/{task_id}/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"

    zf = zipfile.ZipFile(BytesIO(resp.content))
    names = zf.namelist()
    assert "note.md" in names
    assert "transcript.srt" in names
    assert "mindmap.mmd" in names
    assert zf.read("note.md") == b"# md"


def test_export_empty_task_404(client):
    """无产物时导出应 404。"""
    task_id = _make_task(client)
    resp = client.get(f"/api/v1/tasks/{task_id}/export")
    assert resp.status_code == 404
