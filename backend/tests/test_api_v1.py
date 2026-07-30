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
from src.api.v1 import asr as asr_api
from src.api.v1 import settings as settings_api
from src.db.database import Database
from src.models.task import TaskStatus
from src.runtime import task_service as task_service_mod
from src.runtime import worker as worker_mod
from src.api.v1 import tasks as tasks_api


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
    monkeypatch.delenv("VID2NOTE_MASTER_KEY", raising=False)
    monkeypatch.delenv("VID2NOTE_MASTER_KEY_FILE", raising=False)

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
        assert body["version"]
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
    def test_get_exposes_provider_metadata_and_status_without_plaintext(self, client):
        saved = client.put(
            "/api/v1/settings/credentials",
            json={"provider": "deepseek", "field": "api_key", "value": "sk-secret-a1b2"},
        )
        assert saved.status_code == 200, saved.text

        r = client.get("/api/v1/settings")
        assert r.status_code == 200
        body = r.json()
        assert len(body["providers"]) == 9
        assert {item["id"] for item in body["providers"]} == {
            "deepseek",
            "qwen",
            "glm",
            "moonshot",
            "baidu",
            "doubao",
            "minimax",
            "ollama",
            "custom",
        }
        state = body["credentials"]["deepseek"]["api_key"]
        assert state == {"configured": True, "masked": "••••••••a1b2", "source": "encrypted"}
        serialized = __import__("json").dumps(body, ensure_ascii=False)
        assert "sk-secret-a1b2" not in serialized
        assert body["settings"]["concurrency.max"] == "1"
        assert "settings.json" in body["storage"]["settings_path"]
        assert "credentials.enc" in body["storage"]["credentials_path"]

    def test_put_valid_persists_to_settings_file_not_sqlite(self, client):
        r = client.put("/api/v1/settings", json={"concurrency.max": 2, "pdf.mode": "pypdf"})
        assert r.status_code == 200, r.text
        updated = r.json()["updated"]
        assert "concurrency.max" in updated and "pdf.mode" in updated
        settings_path = Path(os.environ["DATA_ROOT"]) / "config" / "settings.json"
        assert settings_path.exists()
        stored = __import__("json").loads(settings_path.read_text(encoding="utf-8"))
        assert stored["settings"]["concurrency.max"] == "2"
        assert _svc().repo.get_setting("concurrency.max") is None

    def test_put_invalid_concurrency_rejected(self, client):
        r = client.put("/api/v1/settings", json={"concurrency.max": 9})
        assert r.status_code == 400
        current = client.get("/api/v1/settings").json()["settings"]
        assert current["concurrency.max"] == "1"

    def test_put_invalid_enum_rejected(self, client):
        r = client.put("/api/v1/settings", json={"pdf.mode": "weird"})
        assert r.status_code == 400
        detail = client.put(
            "/api/v1/settings", json={"note.detail_level": "encyclopedic"}
        )
        assert detail.status_code == 400

    def test_put_asr_config_scalar_rejected(self, client):
        r = client.put("/api/v1/settings", json={"asr.config": "not-an-object"})
        assert r.status_code == 400

    def test_put_unknown_provider_rejected(self, client):
        r = client.put("/api/v1/settings", json={"llm.provider": "not-a-provider"})
        assert r.status_code == 400

    def test_put_is_atomic_when_one_field_is_invalid(self, client):
        assert client.put("/api/v1/settings", json={"concurrency.max": 2}).status_code == 200
        r = client.put(
            "/api/v1/settings",
            json={"concurrency.max": 3, "advanced.temperature": 8},
        )
        assert r.status_code == 400
        current = client.get("/api/v1/settings").json()["settings"]
        assert current["concurrency.max"] == "2"

    def test_provider_profile_is_editable_and_validated(self, client):
        r = client.put(
            "/api/v1/settings",
            json={
                "llm.providers": {
                    "deepseek": {
                        "model": "my-model",
                        "base_url": "https://llm.example.test/v1",
                        "timeout": 45,
                    }
                }
            },
        )
        assert r.status_code == 200, r.text
        profile = r.json()["profiles"]["deepseek"]
        assert profile["model"] == "my-model"
        assert profile["base_url"] == "https://llm.example.test/v1"
        assert profile["timeout"] == 45

        invalid = client.put(
            "/api/v1/settings",
            json={"llm.providers": {"custom": {"model": "", "base_url": "javascript:x"}}},
        )
        assert invalid.status_code == 400

    def test_credential_save_reveal_clear_and_no_store(self, client):
        saved = client.put(
            "/api/v1/settings/credentials",
            json={"provider": "qwen", "field": "api_key", "value": "sk-visible-on-demand"},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["state"]["configured"] is True

        reveal = client.post(
            "/api/v1/settings/credentials/reveal",
            json={"provider": "qwen", "field": "api_key"},
        )
        assert reveal.status_code == 200
        assert reveal.json() == {"value": "sk-visible-on-demand"}
        assert "no-store" in reveal.headers["cache-control"]

        cleared = client.delete("/api/v1/settings/credentials/qwen/api_key")
        assert cleared.status_code == 200
        assert cleared.json()["state"]["configured"] is False
        missing = client.post(
            "/api/v1/settings/credentials/reveal",
            json={"provider": "qwen", "field": "api_key"},
        )
        assert missing.status_code == 404

    def test_credential_field_whitelist_rejects_illegal_field(self, client):
        saved = client.put(
            "/api/v1/settings/credentials",
            json={
                "provider": "deepseek",
                "field": "base_url",
                "value": "https://attacker.invalid",
            },
        )
        revealed = client.post(
            "/api/v1/settings/credentials/reveal",
            json={"provider": "deepseek", "field": "base_url"},
        )
        assert saved.status_code == 400
        assert revealed.status_code == 400

    def test_empty_credential_does_not_overwrite_existing(self, client):
        client.put(
            "/api/v1/settings/credentials",
            json={"provider": "glm", "field": "api_key", "value": "keep-me"},
        )
        r = client.put(
            "/api/v1/settings/credentials",
            json={"provider": "glm", "field": "api_key", "value": ""},
        )
        assert r.status_code == 200
        reveal = client.post(
            "/api/v1/settings/credentials/reveal",
            json={"provider": "glm", "field": "api_key"},
        )
        assert reveal.json()["value"] == "keep-me"

    def test_llm_connection_test_uses_saved_profile_and_secret(self, client, monkeypatch):
        client.put(
            "/api/v1/settings/credentials",
            json={"provider": "deepseek", "field": "api_key", "value": "sk-connect"},
        )
        client.put(
            "/api/v1/settings",
            json={
                "llm.providers": {
                    "deepseek": {
                        "model": "test-model",
                        "base_url": "https://llm.example.test/v1",
                        "timeout": 15,
                    }
                }
            },
        )
        captured = {}

        class FakeLLM:
            def chat(self, messages, **kwargs):
                captured["messages"] = messages
                captured["chat_kwargs"] = kwargs
                return "OK"

        def fake_create(provider, config):
            captured["provider"] = provider
            captured["config"] = config
            return FakeLLM()

        monkeypatch.setattr(settings_api.LLMFactory, "create", fake_create)
        r = client.post("/api/v1/settings/llm/test", json={"provider": "deepseek"})

        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        assert captured["provider"] == "deepseek"
        assert captured["config"]["api_key"] == "sk-connect"
        assert captured["config"]["model"] == "test-model"
        assert captured["config"]["base_url"] == "https://llm.example.test/v1"
        assert captured["config"]["timeout"] == 15
        assert captured["chat_kwargs"]["max_tokens"] <= 8

    @pytest.mark.parametrize(
        ("error", "category"),
        [
            (TimeoutError("request timed out"), "timeout"),
            (RuntimeError("401 Unauthorized sk-secret-must-not-leak"), "authentication"),
        ],
    )
    def test_llm_connection_failure_is_categorized_and_sanitized(
        self, client, monkeypatch, error, category
    ):
        client.put(
            "/api/v1/settings/credentials",
            json={
                "provider": "qwen",
                "field": "api_key",
                "value": "sk-secret-must-not-leak",
            },
        )

        class FailingLLM:
            def chat(self, _messages, **_kwargs):
                raise error

        monkeypatch.setattr(
            settings_api.LLMFactory,
            "create",
            lambda _provider, _config: FailingLLM(),
        )
        r = client.post("/api/v1/settings/llm/test", json={"provider": "qwen"})
        assert r.status_code == 200
        assert r.json()["ok"] is False
        assert r.json()["category"] == category
        assert "sk-secret-must-not-leak" not in r.text


# --------------------------------------------------------------------------- #
# tasks:创建 / 详情 / 历史
# --------------------------------------------------------------------------- #
class TestTasksCrud:
    def test_create_online(self, client):
        r = client.post(
            "/api/v1/tasks",
            data={
                "source_url": "https://www.youtube.com/watch?v=abc123",
                "note_detail_level": "detailed",
            },
        )
        assert r.status_code == 201, r.text
        task = r.json()
        assert task["source_type"] == "youtube"
        assert task["status"] == "pending"
        assert task["note_detail_level"] == "detailed"
        assert task["id"].startswith("task_")
        tid = task["id"]

        # 详情
        r2 = client.get(f"/api/v1/tasks/{tid}")
        assert r2.status_code == 200
        assert r2.json()["id"] == tid

    def test_create_unrecognized_400(self, client):
        r = client.post("/api/v1/tasks", data={"source_url": "totally not a url"})
        assert r.status_code == 400

    def test_create_local_media_upload(self, client):
        r = client.post(
            "/api/v1/tasks",
            files={"file": ("clip.mp4", b"\x00\x00\x00\x20ftyp-test", "video/mp4")},
        )
        assert r.status_code == 201, r.text
        task = r.json()
        assert task["source_type"] == "local_video"
        staging = _svc().data_root / "temp" / "_staging"
        assert not list(staging.glob("*"))

    def test_rejects_unsupported_upload(self, client):
        r = client.post(
            "/api/v1/tasks",
            files={"file": ("notes.txt", b"not media", "text/plain")},
        )
        assert r.status_code == 400

    def test_rejects_oversized_upload(self, client, monkeypatch):
        monkeypatch.setattr(tasks_api, "MAX_MEDIA_UPLOAD_BYTES", 4)
        r = client.post(
            "/api/v1/tasks",
            files={"file": ("clip.mp4", b"12345", "video/mp4")},
        )
        assert r.status_code == 400
        staging = _svc().data_root / "temp" / "_staging"
        assert not list(staging.glob("*"))

    def test_rejects_fake_pdf(self, client):
        r = client.post(
            "/api/v1/tasks",
            data={"source_url": "https://youtu.be/pdf-test"},
            files={"pdf": ("lecture.pdf", b"not a pdf", "application/pdf")},
        )
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
        assert "event: task-missing" in r.text
        assert "task-missing" in r.text

    def test_stream_terminal_task(self, client):
        tid = client.post(
            "/api/v1/tasks", data={"source_url": "https://youtu.be/s1"}
        ).json()["id"]
        _svc().repo.update(tid, status=TaskStatus.COMPLETED.value, progress=100)
        r = client.get(f"/api/v1/tasks/{tid}/stream")
        assert r.status_code == 200
        assert "event: snapshot" in r.text
        assert "event: task-completed" in r.text
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
    def test_legacy_model_path_is_normalized_before_asr_form_round_trip(
        self, client
    ):
        settings_api.SettingsStore().write(
            {"asr.config": {"model_path": "/app/data/models/legacy-whisper"}}
        )

        current = client.get("/api/v1/settings")
        assert current.status_code == 200
        asr_config = current.json()["settings"]["asr.config"]
        assert asr_config["whisper_model_path"] == "/app/data/models/legacy-whisper"
        assert "model_path" not in asr_config

        saved = client.put(
            "/api/v1/settings",
            json={"asr.engine": "whisper_cpp", "asr.config": asr_config},
        )
        assert saved.status_code == 200, saved.text
        stored = settings_api.SettingsStore().read()["asr.config"]
        assert stored["whisper_model_path"] == "/app/data/models/legacy-whisper"
        assert "model_path" not in stored

    def test_asr_config_is_validated_atomically_and_external_key_is_encrypted(
        self, client
    ):
        valid = {
            "whisper_model_path": "/app/data/models/ggml-small.bin",
            "whisper_binary": "/usr/local/bin/whisper-cli",
            "whisper_language": "zh",
            "external_endpoint": "https://asr.example.test/v1/transcribe",
            "external_timeout": 45,
            "vad_threshold_seconds": 240,
            "vad_target_segment_seconds": 90,
            "concurrency": 2,
            "request_timeout": 180,
        }
        saved = client.put("/api/v1/settings", json={"asr.config": valid})
        assert saved.status_code == 200, saved.text
        key_saved = client.put(
            "/api/v1/settings/credentials",
            json={
                "provider": "external_asr",
                "field": "api_key",
                "value": "asr-encrypted-key",
            },
        )
        assert key_saved.status_code == 200
        body = client.get("/api/v1/settings").json()
        assert body["settings"]["asr.config"]["concurrency"] == 2
        assert body["sensitive"]["external_asr"]["api_key"]["configured"] is True
        public_file = (
            Path(os.environ["DATA_ROOT"]) / "config" / "settings.json"
        ).read_text(encoding="utf-8")
        encrypted_file = (
            Path(os.environ["DATA_ROOT"]) / "config" / "credentials.enc"
        ).read_bytes()
        assert "asr-encrypted-key" not in public_file
        assert b"asr-encrypted-key" not in encrypted_file

        invalid = client.put(
            "/api/v1/settings",
            json={
                "asr.config": {"vad_threshold_seconds": 5},
                "asr.engine": "external",
            },
        )
        assert invalid.status_code == 400
        after = client.get("/api/v1/settings").json()["settings"]
        assert after["asr.engine"] == "bcut"
        assert after["asr.config"]["vad_threshold_seconds"] == 240

    @pytest.mark.parametrize(
        "bad_config",
        [
            {"external_endpoint": "file:///etc/passwd"},
            {"external_timeout": 0},
            {"concurrency": 9},
            {"vad_target_segment_seconds": 5},
            {"whisper_device": "cuda"},
            {"whisper_compute_type": "float16"},
        ],
    )
    def test_asr_config_rejects_invalid_fields(self, client, bad_config):
        r = client.put("/api/v1/settings", json={"asr.config": bad_config})
        assert r.status_code == 400

    def test_status_three_engines(self, client):
        client.put(
            "/api/v1/settings",
            json={
                "asr.engine": "external",
                "asr.strategy": "single",
                "asr.config": {
                    "whisper_model_path": "/missing/model.bin",
                    "whisper_binary": "/missing/whisper-cli",
                    "whisper_language": "en",
                    "external_endpoint": "https://asr.example.test/v1",
                    "external_timeout": 33,
                    "vad_threshold_seconds": 360,
                    "vad_target_segment_seconds": 120,
                    "concurrency": 2,
                },
            },
        )
        r = client.get("/api/v1/asr/status")
        assert r.status_code == 200
        d = r.json()
        assert {"bcut", "whisper_cpp", "external"} <= set(d.keys())
        assert d["bcut"]["available"] is True
        assert d["bcut"]["experimental"] is True
        assert "model_exists" in d["whisper_cpp"]
        assert d["whisper_cpp"]["binary_exists"] is False
        assert d["whisper_cpp"]["language"] == "en"
        assert "endpoint_configured" in d["external"]
        assert "endpoint" not in d["external"]
        assert d["external"]["endpoint_host"] == "asr.example.test"
        assert d["external"]["timeout"] == 33
        assert d["selection"] == {"engine": "external", "strategy": "single"}
        assert d["vad"]["threshold_seconds"] == 360
        assert d["vad"]["target_segment_seconds"] == 120
        assert d["vad"]["concurrency"] == 2

    def test_test_bad_engine_400(self, client):
        r = client.post("/api/v1/asr/test", json={"engine": "nope"})
        assert r.status_code == 400

    def test_test_bcut_uses_bilibili_probe(self, client, monkeypatch):
        calls = []

        class ProbeResponse:
            status_code = 200

        def fake_get(url, **kwargs):
            calls.append((url, kwargs))
            return ProbeResponse()

        monkeypatch.setattr(asr_api.requests, "get", fake_get)
        r = client.post("/api/v1/asr/test", json={"engine": "bcut"})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert r.json()["message"] == "bcut 可达"
        assert calls[0][0] == asr_api._BCUT_PROBE_URL
        assert calls[0][1]["allow_redirects"] is False

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
