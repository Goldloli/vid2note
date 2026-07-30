"""LLM 用量观测测试(openspec change add-llm-usage-observability)。

覆盖:
- normalize_usage 四种形态(DeepSeek 缓存字段 / OpenAI cached_tokens /
  无缓存字段 / usage 为 None)与 chat() 暂存 last_usage。
- SimpleProcessor._call_llm 的 usage_callback 上报、无 last_usage 降级、
  回调异常不中断。
- classify_llm_operation 阶段映射与 LlmUsageAggregator 两级累计。
- 仓库 create/update llm_usage 往返、旧库 ALTER 迁移、详情 API 透出。
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1 import v1_router
from src.core.simple_processor import SimpleProcessor
from src.db.database import Database
from src.db.task_repository import TaskRepository
from src.llm.deepseek import DeepSeekLLM
from src.llm.openai_compatible import normalize_usage
from src.models.task import Task
from src.runtime import task_service as task_service_mod
from src.runtime.runner import LlmUsageAggregator, classify_llm_operation


def _usage(prompt=1000, completion=200, hit=100, miss=900):
    """构造一份归一化 usage dict(normalize_usage 的产出形态)。"""
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cache_hit_tokens": hit,
        "cache_miss_tokens": miss,
    }


# --------------------------------------------------------------------------- #
# normalize_usage 归一化
# --------------------------------------------------------------------------- #
class TestNormalizeUsage:
    def test_deepseek_cache_fields(self):
        usage = SimpleNamespace(
            prompt_tokens=1000,
            completion_tokens=200,
            prompt_cache_hit_tokens=100,
            prompt_cache_miss_tokens=900,
        )
        assert normalize_usage(usage) == _usage()

    def test_openai_cached_tokens_nested(self):
        usage = SimpleNamespace(
            prompt_tokens=500,
            completion_tokens=50,
            prompt_tokens_details=SimpleNamespace(cached_tokens=120),
        )
        assert normalize_usage(usage) == _usage(
            prompt=500, completion=50, hit=120, miss=380
        )

    def test_openai_cached_tokens_details_none(self):
        usage = SimpleNamespace(
            prompt_tokens=500,
            completion_tokens=50,
            prompt_tokens_details=None,
        )
        assert normalize_usage(usage) == _usage(prompt=500, completion=50, hit=0, miss=500)

    def test_no_cache_fields_falls_back_to_prompt_tokens(self):
        usage = SimpleNamespace(prompt_tokens=500, completion_tokens=50)
        assert normalize_usage(usage) == _usage(prompt=500, completion=50, hit=0, miss=500)

    def test_none_usage_returns_none(self):
        assert normalize_usage(None) is None


# --------------------------------------------------------------------------- #
# chat() 暂存 last_usage
# --------------------------------------------------------------------------- #
class _FakeClient:
    """openai.OpenAI 桩:chat.completions.create 返回固定响应。"""

    def __init__(self, response, **_kwargs):
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=lambda **_kw: response)
        )

    def with_options(self, **_kwargs):
        return self


def _fake_response(usage):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
        usage=usage,
    )


class TestChatLastUsage:
    def test_chat_stores_normalized_last_usage(self, monkeypatch):
        from src.llm import openai_compatible as compatible

        usage = SimpleNamespace(
            prompt_tokens=1000,
            completion_tokens=200,
            prompt_cache_hit_tokens=100,
            prompt_cache_miss_tokens=900,
        )
        monkeypatch.setattr(compatible, "OpenAI", lambda **kw: _FakeClient(_fake_response(usage)))
        llm = DeepSeekLLM(api_key="sk-test")
        assert llm.last_usage is None
        assert llm.chat([{"role": "user", "content": "hi"}]) == "ok"
        assert llm.last_usage == _usage()

    def test_chat_last_usage_none_when_response_has_no_usage(self, monkeypatch):
        from src.llm import openai_compatible as compatible

        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )
        monkeypatch.setattr(compatible, "OpenAI", lambda **kw: _FakeClient(response))
        llm = DeepSeekLLM(api_key="sk-test")
        assert llm.chat([{"role": "user", "content": "hi"}]) == "ok"
        assert llm.last_usage is None


# --------------------------------------------------------------------------- #
# _call_llm 用量上报
# --------------------------------------------------------------------------- #
class _UsageLLM:
    """带 last_usage 的 LLM 桩(仿 test_note_detail.RecordingLLM)。"""

    def __init__(self, usage=None):
        self.calls = []
        self.last_usage = usage

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return "# 测试笔记"


class TestCallLlmUsageReport:
    def test_reports_each_call_with_operation_name(self):
        llm = _UsageLLM(usage=_usage(prompt=10, completion=5, hit=4, miss=6))
        seen = []
        processor = SimpleProcessor(
            llm,
            config={"usage_callback": lambda op, u: seen.append((op, u))},
        )
        result = processor._call_llm(
            [{"role": "user", "content": "hi"}], operation_name="测试操作"
        )
        assert result == "# 测试笔记"
        assert seen == [("测试操作", _usage(prompt=10, completion=5, hit=4, miss=6))]

    def test_silent_when_adapter_has_no_last_usage(self):
        class BareLLM:  # 无 last_usage 属性(mock / 本地模型场景)
            def chat(self, messages, **kwargs):
                return "ok"

        seen = []
        processor = SimpleProcessor(
            BareLLM(),
            config={"usage_callback": lambda op, u: seen.append((op, u))},
        )
        assert processor._call_llm([]) == "ok"
        assert seen == []

    def test_silent_when_last_usage_is_none(self):
        llm = _UsageLLM(usage=None)
        seen = []
        processor = SimpleProcessor(
            llm,
            config={"usage_callback": lambda op, u: seen.append((op, u))},
        )
        assert processor._call_llm([]) == "# 测试笔记"
        assert seen == []

    def test_callback_error_does_not_interrupt(self):
        llm = _UsageLLM(usage=_usage())

        def boom(_op, _usage):
            raise RuntimeError("采集失败")

        processor = SimpleProcessor(llm, config={"usage_callback": boom})
        assert processor._call_llm([]) == "# 测试笔记"

    def test_no_callback_keeps_existing_behavior(self):
        llm = _UsageLLM(usage=_usage())
        processor = SimpleProcessor(llm)  # 未注入回调
        assert processor._call_llm([]) == "# 测试笔记"


# --------------------------------------------------------------------------- #
# 阶段分类与聚合器
# --------------------------------------------------------------------------- #
class TestClassifyLlmOperation:
    @pytest.mark.parametrize(
        ("operation_name", "stage"),
        [
            ("超详细字幕理解(1/5)", "understand"),
            ("超详细语义证据 ID 修复(2/5)", "understand"),
            ("超详细课程知识蓝图", "blueprint"),
            ("超详细课程知识蓝图 JSON 修复", "blueprint"),
            ("超详细课程知识蓝图修复", "blueprint"),
            ("超详细章节初稿(1/3)", "draft"),
            ("超详细章节审校(1/3)", "review"),
            ("超详细章节格式修复(1/3)", "review"),
            ("超详细章节术语保真(1/3)", "review"),
            ("思维导图大纲生成", "mindmap"),
            ("PDF结构分析", "other"),
            ("笔记生成(PDF参考)", "other"),
            ("笔记生成(直接)", "other"),
            ("", "other"),
            (None, "other"),
        ],
    )
    def test_stage_mapping(self, operation_name, stage):
        assert classify_llm_operation(operation_name) == stage


class TestLlmUsageAggregator:
    def test_two_level_accumulation(self):
        agg = LlmUsageAggregator()
        agg.record("超详细字幕理解(1/2)", _usage())
        agg.record("超详细字幕理解(2/2)", _usage(prompt=500, completion=50, hit=0, miss=500))
        agg.record("超详细章节初稿(1/1)", _usage(prompt=500, completion=50, hit=0, miss=500))
        agg.record("思维导图大纲生成", _usage(prompt=500, completion=50, hit=0, miss=500))

        data = agg.to_dict()
        assert set(data.keys()) == {"total", "by_stage", "by_operation"}
        assert data["total"] == {
            "calls": 4,
            "prompt_tokens": 2500,
            "completion_tokens": 350,
            "cache_hit_tokens": 100,
            "cache_miss_tokens": 2400,
        }
        assert data["by_stage"]["understand"] == {
            "calls": 2,
            "prompt_tokens": 1500,
            "completion_tokens": 250,
            "cache_hit_tokens": 100,
            "cache_miss_tokens": 1400,
        }
        assert data["by_stage"]["draft"]["calls"] == 1
        assert data["by_stage"]["mindmap"]["calls"] == 1
        assert "blueprint" not in data["by_stage"]

        op = data["by_operation"]["超详细字幕理解(1/2)"]
        assert op["stage"] == "understand"
        assert op["calls"] == 1
        assert data["by_operation"]["思维导图大纲生成"]["stage"] == "mindmap"

    def test_empty_aggregator(self):
        data = LlmUsageAggregator().to_dict()
        assert data["total"]["calls"] == 0
        assert data["by_stage"] == {}
        assert data["by_operation"] == {}


# --------------------------------------------------------------------------- #
# 持久化:仓库往返 + 旧库迁移
# --------------------------------------------------------------------------- #
@pytest.fixture
def repo(tmp_path, monkeypatch):
    """隔离到 tmp DB 的真实 TaskRepository(仿 test_api_v1 的单例重置)。"""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "tasks.db"))
    Database.reset_instance()
    yield TaskRepository()
    Database.reset_instance()


class TestRepositoryLlmUsage:
    def test_create_and_update_round_trip(self, repo):
        task = Task(id="t-usage", source_type="direct")
        repo.create(task)
        assert repo.get_by_id("t-usage").llm_usage == {}

        usage = {
            "total": _usage(prompt=1500, completion=250, hit=100, miss=1400) | {"calls": 2},
            "by_stage": {
                "understand": _usage() | {"calls": 1},
                "mindmap": _usage(prompt=500, completion=50, hit=0, miss=500) | {"calls": 1},
            },
            "by_operation": {
                "超详细字幕理解(1/1)": _usage() | {"calls": 1, "stage": "understand"},
            },
        }
        assert repo.update("t-usage", llm_usage=usage)
        loaded = repo.get_by_id("t-usage")
        assert loaded.llm_usage == usage
        assert loaded.to_dict()["llm_usage"] == usage

    def test_create_with_initial_llm_usage(self, repo):
        usage = {"total": _usage() | {"calls": 1}, "by_stage": {}, "by_operation": {}}
        repo.create(Task(id="t-usage-2", source_type="direct", llm_usage=usage))
        assert repo.get_by_id("t-usage-2").llm_usage == usage


class TestMigrateLlmUsageColumn:
    def test_alter_adds_column_to_old_db(self, tmp_path, monkeypatch):
        from src.db import database as database_mod

        db_path = tmp_path / "old.db"
        conn = sqlite3.connect(db_path)
        # 旧库:当前 v1 全量 schema 去掉 llm_usage 列(含判别列与 note_detail_level)
        old_ddl = "\n".join(
            line
            for line in database_mod._TASKS_DDL.splitlines()
            if "llm_usage" not in line
        )
        conn.execute(old_ddl)
        conn.execute("INSERT INTO tasks (id, source_type) VALUES ('t1', 'direct')")
        conn.commit()
        conn.close()

        monkeypatch.setenv("DB_PATH", str(db_path))
        Database.reset_instance()
        try:
            db = Database()
            cols = {row[1] for row in db.fetchall("PRAGMA table_info(tasks)")}
            assert "llm_usage" in cols
            row = db.fetchone("SELECT llm_usage FROM tasks WHERE id = 't1'")
            assert row["llm_usage"] == "{}"
        finally:
            Database.reset_instance()


# --------------------------------------------------------------------------- #
# 详情 API 透出
# --------------------------------------------------------------------------- #
class TestTaskDetailApiLlmUsage:
    def test_detail_response_contains_llm_usage(self, tmp_path, monkeypatch):
        data_root = tmp_path / "data"
        data_root.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("DATA_ROOT", str(data_root))
        monkeypatch.setenv("DB_PATH", str(tmp_path / "tasks.db"))
        monkeypatch.delenv("VID2NOTE_MASTER_KEY", raising=False)
        monkeypatch.delenv("VID2NOTE_MASTER_KEY_FILE", raising=False)
        Database.reset_instance()
        task_service_mod._service = None
        try:
            repo = TaskRepository()
            usage = {
                "total": _usage() | {"calls": 1},
                "by_stage": {"understand": _usage() | {"calls": 1}},
                "by_operation": {
                    "超详细字幕理解(1/1)": _usage() | {"calls": 1, "stage": "understand"},
                },
            }
            repo.create(Task(id="t-api-usage", source_type="direct", llm_usage=usage))
            repo.create(Task(id="t-api-empty", source_type="direct"))

            app = FastAPI()
            app.include_router(v1_router)
            with TestClient(app) as client:
                resp = client.get("/api/v1/tasks/t-api-usage")
                assert resp.status_code == 200
                payload = resp.json()["llm_usage"]
                assert payload["total"]["calls"] == 1
                assert payload["by_stage"]["understand"]["prompt_tokens"] == 1000
                assert "by_operation" in payload

                resp_empty = client.get("/api/v1/tasks/t-api-empty")
                assert resp_empty.status_code == 200
                assert resp_empty.json()["llm_usage"] == {}
        finally:
            Database.reset_instance()
            task_service_mod._service = None
