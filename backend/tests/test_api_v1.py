"""api.v1 路由集成测试(阶段3·API 与入口)。

用 FastAPI TestClient 跑真实 v1 路由 + 真实 TaskRepository(隔离到 tmp DB/DATA_ROOT),
不启动 worker / 不跑 lifespan(构造仅含 v1_router 的 app)。覆盖:
- health / storage / settings(GET 脱敏 + PUT 逐项校验)。
- tasks:创建(在线链接 / 无法识别 400)、详情(404)、历史、取消(pending)、
  rerun(pending 拒绝 409)、产物下载(防越界 / 缺失 404 / 非法 kind 400)、SSE(终态与缺失)。
- batch:export(zip)。
"""
from __future__ import annotations

import io
import os
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1 import v1_router
from src.db.database import Database
from src.models.task import TaskStatus
from src.runtime import task_service as task_service_mod
from src.runtime import worker as worker_mod


# --------------------------------------------------------------------------- #
# 隔离 fixture:tmp DATA_ROOT + tmp DB,重置 Database / service / worker 单例
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "tasks.db"

    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("DB_PATH", str(db_path))

    # 清掉进程级单例,使后续 TaskRepository()/TaskService() 用新的 env
    Database.reset_instance()
    task_service_mod._service = None
    # worker 单例若存在则停掉并清空(避免跨用例消费队列)
    try:
        if worker_mod._worker is not None:
            import asyncio

            asyncio.run(worker_mod._worker.stop())
    except Exception:  # noqa: BLE001
        pass
    worker_mod._worker = None

    app = FastAPI()
    app.include_router(v1_router)
    with TestClient(app) as c:
        yield c

    # 收尾:清单例,不污染后续用例
    Database.reset_instance()
    task_service_mod._service = None
    worker_mod._worker = None


def _svc():
    return task_service_mod.get_task_service()


# --------------------------------------------------------------------------- #
# health / storage
# --------------------------------------------------------------------------- #
class TestHealthStorage:
    def test_health(self, client):
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "healthy"
        assert "yt-dlp" in body["tools"]
        assert "ffmpeg" in body["tools"]
        assert "asr_engine" in body["engines"]

    def test_storage_stats(self, client):
        r = client.get("/api/v1/storage/stats")
        assert r.status_code == 200
        body = r.json()
        assert "total_bytes" in body
        assert "by_kind" in body
        # 五类齐全
        for kind in ("video", "audio", "srt", "note", "screenshot"):
            assert kind in body["by_kind"]


# --------------------------------------------------------------------------- #
# settings
# --------------------------------------------------------------------------- #
class TestSettings:
    def test_get_masks_credentials(self, client):
        repo = _svc().repo
        repo.set_setting("llm.credentials", '{"deepseek": {"api_key": "sk-secret"}}')
        r = client.get("/api/v1/settings")
        assert r.status_code == 200
        settings = r.json()["settings"]
        assert settings["llm.credentials"] == "***"  # 已配置脱敏
        # 非凭证字段正常返回
        assert settings["concurrency.max"] == "1"

    def test_put_valid_persists(self, client):
        r = client.put("/api/v1/settings", json={"concurrency.max": 2, "pdf.mode": "mineru"})
        assert r.status_code == 200, r.text
        updated = r.json()["updated"]
        assert "concurrency.max" in updated and "pdf.mode" in updated
        # 已落库
        assert _svc().repo.get_setting("concurrency.max") == "2"
        assert _svc().repo.get_setting("pdf.mode") == "mineru"

    def test_put_invalid_concurrency_rejected(self, client):
        r = client.put("/api/v1/settings", json={"concurrency.max": 9})
        assert r.status_code == 400
        # 非法值不落库
        assert _svc().repo.get_setting("concurrency.max") in (None, "1")

    def test_put_invalid_enum_rejected(self, client):
        r = client.put("/api/v1/settings", json={"pdf.mode": "weird"})
        assert r.status_code == 400

    def test_put_credential_mask_not_clobbered(self, client):
        repo = _svc().repo
        repo.set_setting("llm.credentials", '{"deepseek": {"api_key": "sk-real"}}')
        # 前端把脱敏值原样回传 → 跳过,不覆盖
        r = client.put("/api/v1/settings", json={"llm.credentials": "***"})
        assert r.status_code == 200
        assert repo.get_setting("llm.credentials") == '{"deepseek": {"api_key": "sk-real"}}'

    def test_put_credentials_as_dict(self, client):
        r = client.put(
            "/api/v1/settings",
            json={"llm.credentials": {"deepseek": {"api_key": "sk-new"}}},
        )
        assert r.status_code == 200, r.text
        import json as _json

        stored = _json.loads(_svc().repo.get_setting("llm.credentials"))
        assert stored["deepseek"]["api_key"] == "sk-new"


# --------------------------------------------------------------------------- #
# tasks:创建 / 详情 / 历史
# --------------------------------------------------------------------------- #
class TestTasksCrud:
    def test_create_online(self, client):
        r = client.post(
            "/api/v1/tasks",
            data={"source_url": "https://www.youtube.com/watch?v=abc123"},
        )
        assert r.status_code == 201, r.text
        task = r.json()
        assert task["source_type"] == "youtube"
        assert task["status"] == "pending"
        assert task["id"].startswith("task_")
        tid = task["id"]

        # 详情
        r2 = client.get(f"/api/v1/tasks/{tid}")
        assert r2.status_code == 200
        assert r2.json()["id"] == tid

    def test_create_unrecognized_400(self, client):
        r = client.post("/api/v1/tasks", data={"source_url": "totally not a url"})
        assert r.status_code == 400

    def test_get_missing_404(self, client):
        assert client.get("/api/v1/tasks/task_nope00000").status_code == 404

    def test_list_history(self, client):
        client.post("/api/v1/tasks", data={"source_url": "https://youtu.be/x1"})
        client.post("/api/v1/tasks", data={"source_url": "https://youtu.be/x2"})
        r = client.get("/api/v1/tasks")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 2
        assert len(body["items"]) >= 2
        assert "page" in body and "page_size" in body

    def test_list_filter_bad_status_400(self, client):
        assert client.get("/api/v1/tasks", params={"status": "bogus"}).status_code == 400


# --------------------------------------------------------------------------- #
# tasks:队列满(429)—— 默认并发 1 → 容量 2,第 3 个活跃任务被拒
# --------------------------------------------------------------------------- #
class TestQueueFull:
    def test_create_when_queue_full_429(self, client):
        assert client.post("/api/v1/tasks", data={"source_url": "https://youtu.be/q1"}).status_code == 201
        assert client.post("/api/v1/tasks", data={"source_url": "https://youtu.be/q2"}).status_code == 201
        # 容量已满(2 个 pending,无 worker 消费)→ 第 3 个 429
        r = client.post("/api/v1/tasks", data={"source_url": "https://youtu.be/q3"})
        assert r.status_code == 429



# --------------------------------------------------------------------------- #
# tasks:取消 / 重跑
# --------------------------------------------------------------------------- #
class TestTasksCancelRerun:
    def test_cancel_pending(self, client):
        tid = client.post(
            "/api/v1/tasks", data={"source_url": "https://youtu.be/c1"}
        ).json()["id"]
        r = client.post(f"/api/v1/tasks/{tid}/cancel")
        assert r.status_code == 200
        assert r.json()["cancelled"] is True
        assert _svc().get_task(tid).status == TaskStatus.CANCELLED

    def test_cancel_terminal_409(self, client):
        tid = client.post(
            "/api/v1/tasks", data={"source_url": "https://youtu.be/c2"}
        ).json()["id"]
        _svc().repo.update(tid, status=TaskStatus.COMPLETED.value)
        assert client.post(f"/api/v1/tasks/{tid}/cancel").status_code == 409

    def test_rerun_pending_409(self, client):
        tid = client.post(
            "/api/v1/tasks", data={"source_url": "https://youtu.be/r1"}
        ).json()["id"]
        r = client.post(f"/api/v1/tasks/{tid}/rerun", params={"from": "note"})
        assert r.status_code == 409

    def test_rerun_invalid_from_node_409(self, client):
        tid = client.post(
            "/api/v1/tasks", data={"source_url": "https://youtu.be/r2"}
        ).json()["id"]
        _svc().repo.update(tid, status=TaskStatus.FAILED.value)
        r = client.post(f"/api/v1/tasks/{tid}/rerun", params={"from": "bogus"})
        assert r.status_code == 409


# --------------------------------------------------------------------------- #
# tasks:产物下载(防越界)
# --------------------------------------------------------------------------- #
class TestProducts:
    def _make_completed_with_note(self, client) -> str:
        tid = client.post(
            "/api/v1/tasks", data={"source_url": "https://youtu.be/p1"}
        ).json()["id"]
        svc = _svc()
        note_rel = f"notes/{tid}/note.md"
        note_abs = svc.data_root / note_rel
        note_abs.parent.mkdir(parents=True, exist_ok=True)
        note_abs.write_text("# 笔记", encoding="utf-8")
        svc.repo.update(tid, note_path=note_rel, status=TaskStatus.COMPLETED.value)
        return tid

    def test_download_note(self, client):
        tid = self._make_completed_with_note(client)
        r = client.get(f"/api/v1/tasks/{tid}/products/note")
        assert r.status_code == 200
        assert "笔" in r.text

    def test_download_missing_product_404(self, client):
        tid = client.post(
            "/api/v1/tasks", data={"source_url": "https://youtu.be/p2"}
        ).json()["id"]
        r = client.get(f"/api/v1/tasks/{tid}/products/note")
        assert r.status_code == 404

    def test_download_bad_kind_400(self, client):
        tid = client.post(
            "/api/v1/tasks", data={"source_url": "https://youtu.be/p3"}
        ).json()["id"]
        assert client.get(f"/api/v1/tasks/{tid}/products/secret").status_code == 400

    def test_download_pdf_inline(self, client):
        # PDF 讲义经笔记页 iframe 内联预览,需 200 + application/pdf 且不带 attachment
        tid = client.post(
            "/api/v1/tasks", data={"source_url": "https://youtu.be/pp"}
        ).json()["id"]
        svc = _svc()
        pdf_rel = f"pdfs/{tid}/handout.pdf"
        pdf_abs = svc.data_root / pdf_rel
        pdf_abs.parent.mkdir(parents=True, exist_ok=True)
        pdf_abs.write_bytes(b"%PDF-1.4 dummy")
        svc.repo.update(tid, pdf_path=pdf_rel, status=TaskStatus.COMPLETED.value)
        r = client.get(f"/api/v1/tasks/{tid}/products/pdf")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert "attachment" not in r.headers.get("content-disposition", "")


# --------------------------------------------------------------------------- #
# tasks:SSE 流(缺失 + 终态两条可即时关闭的路径)
# --------------------------------------------------------------------------- #
class TestStream:
    def test_stream_missing_task(self, client):
        r = client.get("/api/v1/tasks/task_missing000/stream")
        assert r.status_code == 200
        assert "task-missing" in r.text

    def test_stream_terminal_task(self, client):
        tid = client.post(
            "/api/v1/tasks", data={"source_url": "https://youtu.be/s1"}
        ).json()["id"]
        _svc().repo.update(tid, status=TaskStatus.COMPLETED.value, progress=100)
        r = client.get(f"/api/v1/tasks/{tid}/stream")
        assert r.status_code == 200
        assert "snapshot" in r.text
        assert "task-completed" in r.text


# --------------------------------------------------------------------------- #
# batch:export(zip)
# --------------------------------------------------------------------------- #
class TestBatch:
    def test_export_zip(self, client):
        tid = client.post(
            "/api/v1/tasks", data={"source_url": "https://youtu.be/b1"}
        ).json()["id"]
        svc = _svc()
        note_rel = f"notes/{tid}/note.md"
        note_abs = svc.data_root / note_rel
        note_abs.parent.mkdir(parents=True, exist_ok=True)
        note_abs.write_text("# 导出笔记", encoding="utf-8")
        svc.repo.update(tid, note_path=note_rel, status=TaskStatus.COMPLETED.value)

        r = client.post("/api/v1/tasks/batch", json={"action": "export", "task_ids": [tid]})
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        assert any("note.md" in n for n in zf.namelist())

    def test_batch_bad_action_400(self, client):
        r = client.post("/api/v1/tasks/batch", json={"action": "nope", "task_ids": []})
        assert r.status_code == 400


# --------------------------------------------------------------------------- #
# asr:status / test(openspec change asr-management-page)
# --------------------------------------------------------------------------- #
class TestAsr:
    def test_status_three_engines(self, client):
        r = client.get("/api/v1/asr/status")
        assert r.status_code == 200
        d = r.json()
        assert {"asrtools", "whisper_cpp", "external"} <= set(d.keys())
        assert d["asrtools"]["available"] is True
        assert d["asrtools"]["provider"] == "bcut"  # 默认 provider 改为必剪
        assert "model_exists" in d["whisper_cpp"]
        assert "endpoint_configured" in d["external"]

    def test_test_bad_engine_400(self, client):
        r = client.post("/api/v1/asr/test", json={"engine": "nope"})
        assert r.status_code == 400

    def test_test_whisper_missing_model(self, client):
        # 默认未配置 whisper 模型 → ok=False(不发网络)
        r = client.post("/api/v1/asr/test", json={"engine": "whisper_cpp"})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is False
        assert "latency_ms" in d
        assert "模型" in d["message"] or "未配置" in d["message"]

    def test_test_external_not_configured(self, client):
        r = client.post("/api/v1/asr/test", json={"engine": "external"})
        assert r.status_code == 200
        assert r.json()["ok"] is False


# --------------------------------------------------------------------------- #
# tasks:stats(openspec change console-history-detail-nav)
# --------------------------------------------------------------------------- #
class TestStats:
    def test_stats_shape_and_counts(self, client):
        for u in ["https://youtu.be/s1", "https://youtu.be/s2"]:
            client.post("/api/v1/tasks", data={"source_url": u})
        r = client.get("/api/v1/tasks/stats")
        assert r.status_code == 200
        d = r.json()
        assert {"running", "today_completed", "total", "completed"} <= set(d.keys())
        assert d["total"] >= 2
        assert d["running"] >= 2  # 新建任务为 pending,计入 running
