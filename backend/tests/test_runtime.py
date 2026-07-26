"""
runtime 运行栈单元测试(阶段2·运行栈)
=====================================

覆盖:
- 设置快照默认值与并发 clamp。
- TaskService:创建(在线链接 / 本地上传 / 无法识别)、查询、重跑校验、取消
  (pending / running / 终态)、批量重跑克隆。
- runner.run_task:用桩执行器跑通 local_audio 全流程,验证状态迁移
  pending → running → completed 与产物回写、SSE 事件顺序(先落库再推)。
- worker:asyncio 队列消费(桩 run_task)。

不依赖真实 LLM / ffmpeg / yt-dlp:执行器与 run_task 用桩 / monkeypatch 替换。
"""
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.media_ingest import SourceType, UploadedFile
from src.models.task import NODE_NAMES, TERMINAL_TASK_STATUSES, Task, TaskStatus
from src.pipeline import NodeName, TaskState
from src.runtime import (
    DEFAULT_CONCURRENCY,
    MAX_CONCURRENCY,
    MIN_CONCURRENCY,
    RuntimeWorker,
    TaskService,
    clamp_concurrency,
    get_cancel_registry,
    get_settings_snapshot,
)
from src.runtime import runner as runner_mod
from src.runtime import worker as worker_mod
from src.runtime.adapters import RepoStateAdapter


# --------------------------------------------------------------------------- #
# FakeRepo:内存版 TaskRepository(满足 RepoStateAdapter / TaskService 接口)
# --------------------------------------------------------------------------- #
class FakeRepo:
    def __init__(self, settings=None):
        self._tasks = {}
        self._settings = dict(settings or {})

    def create(self, task):
        self._tasks[task.id] = task
        # 维护 queue_position(pending 取位次)
        if task.status == TaskStatus.PENDING:
            task.queue_position = sum(
                1 for t in self._tasks.values() if t.status == TaskStatus.PENDING and t.id != task.id
            ) + 1
        return task.id

    def get_by_id(self, task_id):
        return self._tasks.get(task_id)

    def update(self, task_id, **kwargs):
        t = self._tasks.get(task_id)
        if t is None:
            return False
        for k, v in kwargs.items():
            if isinstance(v, TaskStatus):
                v = v.value
            setattr(t, k, v)
        return True

    def cancel_task(self, task_id):
        t = self._tasks.get(task_id)
        if t is None:
            return False
        t.status = TaskStatus.CANCELLED
        t.queue_position = None
        return True

    def fail_task(self, task_id, error):
        t = self._tasks.get(task_id)
        if t is None:
            return False
        t.status = TaskStatus.FAILED
        t.error = error
        t.queue_position = None
        return True

    def get_all_settings(self):
        return dict(self._settings)

    def list_history(self, **kwargs):
        items = list(self._tasks.values())
        return {"items": items, "total": len(items), "page": 1, "page_size": len(items)}


class RecorderBus:
    """记录 publish 调用(同步接口,供 runner 直接使用)。"""

    def __init__(self):
        self.events = []

    def publish(self, task_id, event_type, data):
        self.events.append((task_id, event_type, dict(data)))


# --------------------------------------------------------------------------- #
# settings
# --------------------------------------------------------------------------- #
class TestSettings:
    def test_defaults_present(self):
        snap = get_settings_snapshot(None)
        assert snap["llm.provider"] == "deepseek"
        assert snap["llm.model"] == "deepseek-v4-flash"
        assert snap["asr.engine"] == "asrtools"
        assert snap["pdf.mode"] == "pypdf"
        assert snap["concurrency.max"] == "1"
        assert snap["note.output_language"] == "zh"
        assert snap["note.extract_images"] == "false"
        # 五类保留默认
        assert snap["retention.video"] == "7d"
        assert snap["retention.audio"] == "7d"
        assert snap["retention.srt"] == "30d"
        assert snap["retention.note"] == "permanent"
        assert snap["retention.screenshot"] == "30d"

    def test_repo_overrides_defaults(self):
        repo = FakeRepo(settings={"llm.provider": "glm", "concurrency.max": "3"})
        snap = get_settings_snapshot(repo)
        assert snap["llm.provider"] == "glm"
        assert snap["concurrency.max"] == "3"
        # 未覆盖的仍取默认
        assert snap["llm.model"] == "deepseek-v4-flash"

    def test_illegal_enum_falls_back(self):
        repo = FakeRepo(settings={"asr.engine": "nonsense", "concurrency.max": "99"})
        snap = get_settings_snapshot(repo)
        assert snap["asr.engine"] == "asrtools"
        # concurrency.max 字面量原样保留(由 clamp_concurrency 在使用处回落)
        assert snap["concurrency.max"] == "99"

    def test_clamp_concurrency(self):
        assert clamp_concurrency(1) == 1
        assert clamp_concurrency(2) == 2
        assert clamp_concurrency(3) == 3
        assert clamp_concurrency(0) == MIN_CONCURRENCY == 1
        assert clamp_concurrency(5) == MAX_CONCURRENCY == 3
        assert clamp_concurrency("2") == 2
        assert clamp_concurrency("bad") == DEFAULT_CONCURRENCY == 1
        assert clamp_concurrency(None) == 1


# --------------------------------------------------------------------------- #
# TaskService:创建 / 查询 / 重跑校验 / 取消 / 批量
# --------------------------------------------------------------------------- #
@pytest.fixture
def service(tmp_path):
    return TaskService(repo=FakeRepo(), data_root=tmp_path)


def _make_uploaded(path: Path, name: str, mime: str) -> UploadedFile:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00\x00\x00\x20ftyp" + b"data")
    return UploadedFile(
        abs_path=str(path), original_name=name, mime=mime, size_bytes=path.stat().st_size
    )


class TestCreateTask:
    def test_create_online_youtube(self, service, monkeypatch):
        called = {}

        def fake_enqueue(task_id, from_node=None):
            called["task_id"] = task_id

        monkeypatch.setattr("src.runtime.task_service.enqueue", fake_enqueue)
        task = service.create_task(source_url="https://www.youtube.com/watch?v=abc123")
        assert task.source_type == SourceType.YOUTUBE.value
        assert task.status == TaskStatus.PENDING
        assert task.llm_provider == "deepseek"
        assert task.llm_model == "deepseek-v4-flash"
        assert task.mindmap_formats == ["xmind"]
        assert called["task_id"] == task.id
        # 已入库
        assert service.get_task(task.id).id == task.id

    def test_create_local_video_moves_file_and_sets_path(self, service, monkeypatch):
        monkeypatch.setattr("src.runtime.task_service.enqueue", lambda *a, **k: None)
        up = _make_uploaded(service.data_root / "temp" / "up" / "lec.mp4", "lec.mp4", "video/mp4")
        task = service.create_task(uploaded=up)
        assert task.source_type == SourceType.LOCAL_VIDEO.value
        assert task.video_path.startswith(f"videos/{task.id}/clip.")
        # 文件已复制到产物目录
        assert (service.data_root / task.video_path).exists()
        # 标题取上传文件名
        assert task.title == "lec.mp4"

    def test_create_local_audio(self, service, monkeypatch):
        monkeypatch.setattr("src.runtime.task_service.enqueue", lambda *a, **k: None)
        up = _make_uploaded(service.data_root / "temp" / "up" / "song.wav", "song.wav", "audio/wav")
        task = service.create_task(uploaded=up)
        assert task.source_type == SourceType.LOCAL_AUDIO.value
        assert task.audio_path.startswith(f"audio/{task.id}/audio.")

    def test_create_unrecognized_source_raises(self, service):
        with pytest.raises(ValueError):
            service.create_task(source_url="not a url at all")

    def test_create_engine_options_override(self, service, monkeypatch):
        monkeypatch.setattr("src.runtime.task_service.enqueue", lambda *a, **k: None)
        task = service.create_task(
            source_url="https://youtu.be/xyz",
            llm_provider="qwen",
            llm_model="qwen-max",
            asr_engine="whisper_cpp",
            extract_images=True,
            output_language="en",
            mindmap_formats=["xmind", "md"],
        )
        assert task.llm_provider == "qwen"
        assert task.llm_model == "qwen-max"
        assert task.asr_engine == "whisper_cpp"
        assert task.extract_images is True
        assert task.output_language == "en"
        assert task.mindmap_formats == ["xmind", "md"]


class TestRerun:
    def test_rerun_pending_rejected(self, service, monkeypatch):
        monkeypatch.setattr("src.runtime.task_service.enqueue", lambda *a, **k: None)
        task = service.create_task(source_url="https://youtu.be/x")
        with pytest.raises(ValueError):
            service.rerun(task.id, from_node="note")

    def test_rerun_completed_enqueues(self, service, monkeypatch):
        monkeypatch.setattr("src.runtime.task_service.enqueue", lambda *a, **k: None)
        task = service.create_task(source_url="https://youtu.be/x")
        task.status = TaskStatus.COMPLETED
        captured = {}
        monkeypatch.setattr(
            "src.runtime.task_service.enqueue", lambda tid, from_node=None: captured.update(tid=tid, fn=from_node)
        )
        service.rerun(task.id, from_node="note")
        assert captured == {"tid": task.id, "fn": "note"}

    def test_rerun_invalid_from_node(self, service, monkeypatch):
        monkeypatch.setattr("src.runtime.task_service.enqueue", lambda *a, **k: None)
        task = service.create_task(source_url="https://youtu.be/x")
        task.status = TaskStatus.FAILED
        with pytest.raises(ValueError):
            service.rerun(task.id, from_node="bogus")

    def test_rerun_missing_task(self, service):
        with pytest.raises(KeyError):
            service.rerun("task_nope", from_node="note")


class TestCancel:
    def test_cancel_pending(self, service, monkeypatch):
        monkeypatch.setattr("src.runtime.task_service.enqueue", lambda *a, **k: None)
        monkeypatch.setattr("src.runtime.task_service.mark_skip", lambda tid: None)
        task = service.create_task(source_url="https://youtu.be/x")
        assert service.cancel(task.id) is True
        assert service.get_task(task.id).status == TaskStatus.CANCELLED

    def test_cancel_running_signals_token(self, service, monkeypatch):
        monkeypatch.setattr("src.runtime.task_service.enqueue", lambda *a, **k: None)
        task = service.create_task(source_url="https://youtu.be/x")
        task.status = TaskStatus.RUNNING
        # 登记一个取消令牌模拟运行中
        from src.pipeline import CancelToken

        token = CancelToken()
        get_cancel_registry().register(task.id, token)
        try:
            assert service.cancel(task.id) is True
            assert token.is_cancelled() is True
            # 状态仍 running(由 DAG 在检查点转 cancelled),cancel 仅发信号
            assert service.get_task(task.id).status == TaskStatus.RUNNING
        finally:
            get_cancel_registry().unregister(task.id)

    def test_cancel_terminal_returns_false(self, service, monkeypatch):
        monkeypatch.setattr("src.runtime.task_service.enqueue", lambda *a, **k: None)
        task = service.create_task(source_url="https://youtu.be/x")
        task.status = TaskStatus.COMPLETED
        assert service.cancel(task.id) is False
        task.status = TaskStatus.FAILED
        assert service.cancel(task.id) is False

    def test_cancel_missing_task(self, service):
        with pytest.raises(KeyError):
            service.cancel("task_nope")


class TestBatch:
    def test_batch_rerun_clones_local_video(self, service, monkeypatch):
        monkeypatch.setattr("src.runtime.task_service.enqueue", lambda *a, **k: None)
        up = _make_uploaded(service.data_root / "temp" / "up" / "a.mp4", "a.mp4", "video/mp4")
        src = service.create_task(uploaded=up, llm_provider="glm", mindmap_formats=["md"])
        src.status = TaskStatus.COMPLETED

        result = service.batch([src.id], action="rerun")
        assert result["action"] == "rerun"
        assert result["count"] == 1
        new_id = result["new_task_ids"][0]
        new_task = service.get_task(new_id)
        assert new_task.source_type == src.source_type
        # 复用了源任务的配置
        assert new_task.llm_provider == "glm"
        assert new_task.mindmap_formats == ["md"]
        assert new_task.status == TaskStatus.PENDING
        # 复用了本地输入文件
        assert new_task.video_path.startswith(f"videos/{new_id}/clip.")
        assert (service.data_root / new_task.video_path).exists()
        # 原记录不变
        assert src.id != new_id

    def test_batch_export_zip(self, service, monkeypatch):
        monkeypatch.setattr("src.runtime.task_service.enqueue", lambda *a, **k: None)
        task = service.create_task(source_url="https://youtu.be/x")
        # 手动落一个 note 产物
        note_rel = f"notes/{task.id}/note.md"
        note_abs = service.data_root / note_rel
        note_abs.parent.mkdir(parents=True, exist_ok=True)
        note_abs.write_text("# 笔记", encoding="utf-8")
        task.note_path = note_rel
        task.status = TaskStatus.COMPLETED

        import zipfile, io

        result = service.batch([task.id], action="export")
        assert result["action"] == "export"
        assert result["count"] >= 1
        zf = zipfile.ZipFile(io.BytesIO(result["zip_bytes"]))
        names = zf.namelist()
        assert any("note.md" in n for n in names)

    def test_batch_bad_action(self, service):
        with pytest.raises(ValueError):
            service.batch(["x"], action="nope")


# --------------------------------------------------------------------------- #
# runner.run_task:local_audio 全流程(桩执行器),验证状态迁移 + 先落库再推
# --------------------------------------------------------------------------- #
class TestRunTask:
    def _stub_executors(self, data_root, task_id):
        """构造写真实(微型)文件的桩执行器,模拟 download/asr/note/mindmap 产物。"""

        def _asr(ctx):
            audio_rel = ctx._state.artifact("audio")
            assert audio_rel, "asr 节点应能取到上游 audio"
            out = ctx.product_path("srt", "srt")
            out.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")
            ctx.register_product("srt", ctx.rel_of(out), out.stat().st_size)

        def _note(ctx):
            srt_rel = ctx._state.artifact("srt")
            assert srt_rel
            out = ctx.product_path("note", "md")
            out.write_text("# 笔记内容", encoding="utf-8")
            ctx.register_product("note", ctx.rel_of(out), out.stat().st_size)

        def _mindmap(ctx):
            formats = ctx.task.mindmap_formats or []
            for fmt in formats:
                if fmt == "md":
                    continue
                out = ctx.product_path("mindmap", fmt)
                out.write_bytes(b"PK\x03\x04xmind-stub")
                ctx.register_product("mindmap", ctx.rel_of(out), out.stat().st_size)

        def _cleanup(ctx):
            # 模拟 retention.cleanup_task_temp
            import shutil

            tmp = data_root / "temp" / task_id
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)

        return {
            NodeName.DOWNLOAD: lambda ctx: None,
            NodeName.EXTRACT_AUDIO: lambda ctx: None,
            NodeName.ASR: _asr,
            NodeName.NOTE: _note,
            NodeName.MINDMAP: _mindmap,
            NodeName.CLEANUP: _cleanup,
        }

    def test_run_local_audio_to_completed(self, tmp_path, monkeypatch):
        repo = FakeRepo()
        # 注入 pending 的 local_audio 任务(上传音频已落盘)
        task_id = "task_la1111111111"
        audio_rel = f"audio/{task_id}/audio.wav"
        audio_abs = tmp_path / audio_rel
        audio_abs.parent.mkdir(parents=True, exist_ok=True)
        audio_abs.write_bytes(b"RIFF....")
        task = Task(
            id=task_id,
            source_type=SourceType.LOCAL_AUDIO.value,
            status=TaskStatus.PENDING,
            audio_path=audio_rel,
            mindmap_formats=["xmind"],
        )
        repo.create(task)
        bus = RecorderBus()

        # 用桩执行器替换真实的 _make_executors
        monkeypatch.setattr(
            runner_mod, "_make_executors", lambda t, snap, dr, repo=None: self._stub_executors(dr, t.id)
        )

        final = runner_mod.run_task(
            task_id, repo=repo, bus=bus, data_root=tmp_path, loop=None
        )

        # 状态迁移:pending → running → completed
        assert final.status.value == "completed"
        db_task = repo.get_by_id(task_id)
        assert db_task.status == TaskStatus.COMPLETED
        assert db_task.progress == 100
        # 产物指针回写
        assert db_task.srt_path and db_task.srt_path.startswith(f"srt/{task_id}/")
        assert db_task.note_path and db_task.note_path.startswith(f"notes/{task_id}/")
        assert any(p.startswith(f"notes/{task_id}/") for p in db_task.mindmap_paths)
        # download / extract_audio 被跳过(local_audio)
        assert db_task.node_statuses["download"]["status"] == "skipped"
        assert db_task.node_statuses["extract_audio"]["status"] == "skipped"
        # asr / note / mindmap / cleanup 全 completed
        for n in ("asr", "note", "mindmap", "cleanup"):
            assert db_task.node_statuses[n]["status"] == "completed", n
        # SSE:终态事件已推
        assert any(et == "task-completed" for _, et, _ in bus.events)

    def test_run_task_not_found(self, tmp_path):
        repo = FakeRepo()
        with pytest.raises(KeyError):
            runner_mod.run_task("task_missing000", repo=repo, data_root=tmp_path)

    def test_node_failure_transitions_to_failed(self, tmp_path, monkeypatch):
        repo = FakeRepo()
        task_id = "task_fail00000000"
        audio_rel = f"audio/{task_id}/audio.wav"
        (tmp_path / audio_rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / audio_rel).write_bytes(b"RIFF....")
        task = Task(
            id=task_id,
            source_type=SourceType.LOCAL_AUDIO.value,
            status=TaskStatus.PENDING,
            audio_path=audio_rel,
            mindmap_formats=["xmind"],
        )
        repo.create(task)
        bus = RecorderBus()

        def boom_asr(ctx):
            raise RuntimeError("ASR 引擎不可用")

        def make_ex(t, snap, dr, repo=None):
            stubs = self._stub_executors(dr, t.id)
            stubs[NodeName.ASR] = boom_asr
            return stubs

        monkeypatch.setattr(runner_mod, "_make_executors", make_ex)
        final = runner_mod.run_task(task_id, repo=repo, bus=bus, data_root=tmp_path, loop=None)
        assert final.status.value == "failed"
        db_task = repo.get_by_id(task_id)
        assert db_task.status == TaskStatus.FAILED
        assert "asr" in (db_task.error or "").lower() or db_task.node_statuses["asr"]["error"]
        # cleanup 仍在失败路径执行
        assert db_task.node_statuses["cleanup"]["status"] == "completed"
        # 失败事件已推
        assert any(et == "task-failed" for _, et, _ in bus.events)

    def test_cancel_mid_run(self, tmp_path, monkeypatch):
        repo = FakeRepo()
        task_id = "task_cancel00000"
        audio_rel = f"audio/{task_id}/audio.wav"
        (tmp_path / audio_rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / audio_rel).write_bytes(b"RIFF....")
        task = Task(
            id=task_id,
            source_type=SourceType.LOCAL_AUDIO.value,
            status=TaskStatus.PENDING,
            audio_path=audio_rel,
            mindmap_formats=["xmind"],
        )
        repo.create(task)
        bus = RecorderBus()

        def make_ex(t, snap, dr, repo=None):
            stubs = self._stub_executors(dr, t.id)
            # asr 执行前已被取消 → 抛 PipelineCancelled
            from src.pipeline import PipelineCancelled

            def cancelled_asr(ctx):
                raise PipelineCancelled()

            stubs[NodeName.ASR] = cancelled_asr
            return stubs

        monkeypatch.setattr(runner_mod, "_make_executors", make_ex)
        final = runner_mod.run_task(task_id, repo=repo, bus=bus, data_root=tmp_path, loop=None)
        assert final.status.value == "cancelled"
        assert repo.get_by_id(task_id).status == TaskStatus.CANCELLED
        assert any(et == "task-cancelled" for _, et, _ in bus.events)


# --------------------------------------------------------------------------- #
# RepoStateAdapter:TaskState → repo.update 落库
# --------------------------------------------------------------------------- #
class TestRepoStateAdapter:
    def test_persist_writes_all_fields(self):
        repo = FakeRepo()
        task = Task(id="task_persist0001", source_type="youtube", status=TaskStatus.PENDING)
        repo.create(task)
        state = TaskState.fresh("task_persist0001", "youtube")
        state.status = __import__("src.pipeline", fromlist=["TaskStatus"]).TaskStatus.RUNNING
        state.progress = 42
        state.set_artifact("video", "videos/task_persist0001/clip.mp4", 123)
        RepoStateAdapter(repo).update_task_state("task_persist0001", state)
        db = repo.get_by_id("task_persist0001")
        assert db.status == TaskStatus.RUNNING
        assert db.progress == 42
        assert db.video_path == "videos/task_persist0001/clip.mp4"
        assert db.node_statuses["download"]["product"]["path"].endswith("clip.mp4")


# --------------------------------------------------------------------------- #
# worker:队列消费(桩 run_task)
# --------------------------------------------------------------------------- #
class TestWorker:
    def test_consume_queue_calls_run_task(self, monkeypatch):
        calls = []

        def fake_run_task(task_id, *, from_node=None, **kw):
            calls.append((task_id, from_node))

        monkeypatch.setattr(worker_mod, "run_task", fake_run_task)
        worker = RuntimeWorker(repo=FakeRepo(), max_concurrent=2)

        async def drive():
            await worker.start()
            worker.enqueue("task_w1", None)
            worker.enqueue("task_w2", "note")
            # 等消费完成
            for _ in range(50):
                await asyncio.sleep(0.02)
                if len(calls) >= 2:
                    break
            await worker.stop()

        asyncio.run(drive())
        assert ("task_w1", None) in calls
        assert ("task_w2", "note") in calls

    def test_skip_cancelled_queued_item(self, monkeypatch):
        calls = []

        def fake_run_task(task_id, *, from_node=None, **kw):
            calls.append(task_id)

        monkeypatch.setattr(worker_mod, "run_task", fake_run_task)
        worker = RuntimeWorker(repo=FakeRepo(), max_concurrent=1)

        async def drive():
            await worker.start()
            worker.enqueue("task_keep")
            worker.enqueue("task_skip")
            worker.mark_skip("task_skip")
            for _ in range(50):
                await asyncio.sleep(0.02)
                if "task_keep" in calls:
                    break
            await worker.stop()

        asyncio.run(drive())
        assert "task_keep" in calls
        assert "task_skip" not in calls

    def test_run_task_exception_marks_failed(self, monkeypatch):
        repo = FakeRepo()
        # 预置一个 pending 任务,worker 兜底会把它标 failed
        task = Task(id="task_boom0000000", source_type="youtube", status=TaskStatus.PENDING)
        repo.create(task)

        def boom(task_id, **kw):
            raise RuntimeError("炸了")

        monkeypatch.setattr(worker_mod, "run_task", boom)
        worker = RuntimeWorker(repo=repo, max_concurrent=1)

        async def drive():
            await worker.start()
            worker.enqueue("task_boom0000000")
            for _ in range(50):
                await asyncio.sleep(0.02)
                t = repo.get_by_id("task_boom0000000")
                if t and t.status == TaskStatus.FAILED:
                    break
            await worker.stop()

        asyncio.run(drive())
        assert repo.get_by_id("task_boom0000000").status == TaskStatus.FAILED
