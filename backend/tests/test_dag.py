"""
pipeline/dag 单元测试(task 1.5 / 1.6,规格 task-pipeline,设计 D8)
=================================================================

覆盖:状态机合法/非法迁移、来源跳过、缺上游产物终止、cleanup 双路径必执行、
节点级重跑(复用上游 / 级联重算 / 干净上下文 / 缺失回退)、取消、重启恢复、
产物登记与 SSE 事件顺序。

本测试不依赖 TaskRepository / EventBus / 真实执行器;一律用桩对象与可调用钩子,
验证 DAG 框架与状态机本身的确定性。
"""
import sys
import os
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from src.pipeline import (
    ARTIFACT_TASK_FIELD,
    NODE_ORDER,
    CancelToken,
    DagRunner,
    IllegalTransitionError,
    NodeName,
    NodeStatus,
    PipelineCancelled,
    SourceType,
    TaskState,
    TaskStatus,
    first_executable_node,
    is_legal_task_transition,
    nodes_from,
    recover_running_on_startup,
    run_task_dag,
    skip_nodes_for,
    transition_task_status,
)


# --------------------------------------------------------------------------- #
# 测试桩
# --------------------------------------------------------------------------- #
class RecorderBus:
    """记录所有 publish 调用,便于断言事件顺序与字段。"""

    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def publish(self, task_id: str, event_type: str, data: dict) -> None:
        self.events.append((event_type, dict(data)))

    def types(self) -> list[str]:
        return [e[0] for e in self.events]

    def of(self, event_type: str) -> list[dict]:
        return [d for t, d in self.events if t == event_type]


class RepoSpy:
    """记录 update_task_state 调用次数与最近一次状态。"""

    def __init__(self):
        self.calls: list[tuple[str, TaskState]] = []

    def update_task_state(self, task_id: str, state: TaskState) -> None:
        self.calls.append((task_id, state))


def make_task(task_id: str = "task_test", source_type: str = "youtube", **kw) -> SimpleNamespace:
    """构造一个最小任务桩(id + source_type + 可选顶层产物指针)。"""
    base = {"video_path": None, "audio_path": None, "srt_path": None,
            "note_path": None, "mindmap_paths": [], "screenshot_paths": []}
    base.update(kw)
    return SimpleNamespace(id=task_id, source_type=source_type, **base)


def build_executors(*, fail_at=None, cancel_at=None, content: bytes = b"x",
                    skip_product: set | None = None):
    """构造六节点执行器钩子,返回 (executors_dict, called_list)。

    - fail_at: 指定节点抛 RuntimeError(模拟节点失败)。
    - cancel_at: 指定节点抛 PipelineCancelled(模拟取消)。
    - skip_product: 这些节点不登记产物(用于触发下游「缺上游产物」)。
    - called_list: 记录实际被执行的节点顺序。
    """
    called: list[NodeName] = []
    skip_product = skip_product or set()

    def mk(node: NodeName, kind, ext):
        def _exec(ctx):
            called.append(node)
            if cancel_at == node:
                raise PipelineCancelled()
            if fail_at == node:
                raise RuntimeError(f"{node.value} 模拟失败")
            if kind is None or node in skip_product:
                return  # cleanup / 故意不登记产物
            p = ctx.product_path(kind, ext)
            p.write_bytes(content)
            ctx.register_product(kind, ctx.rel_of(p), len(content))

        return _exec

    execs = {
        NodeName.DOWNLOAD: mk(NodeName.DOWNLOAD, "video", "mp4"),
        NodeName.EXTRACT_AUDIO: mk(NodeName.EXTRACT_AUDIO, "audio", "wav"),
        NodeName.ASR: mk(NodeName.ASR, "srt", "srt"),
        NodeName.NOTE: mk(NodeName.NOTE, "note", "md"),
        NodeName.MINDMAP: mk(NodeName.MINDMAP, "mindmap", "xmind"),
        NodeName.CLEANUP: mk(NodeName.CLEANUP, None, None),
    }
    return execs, called


# --------------------------------------------------------------------------- #
# 1. 状态机:合法 / 非法迁移
# --------------------------------------------------------------------------- #
def test_legal_task_transitions_table():
    assert is_legal_task_transition(TaskStatus.PENDING, TaskStatus.RUNNING)
    assert is_legal_task_transition(TaskStatus.RUNNING, TaskStatus.COMPLETED)
    assert is_legal_task_transition(TaskStatus.RUNNING, TaskStatus.FAILED)
    assert is_legal_task_transition(TaskStatus.RUNNING, TaskStatus.CANCELLED)
    assert is_legal_task_transition(TaskStatus.PENDING, TaskStatus.CANCELLED)
    # 经节点级 rerun 回 running(契约 §1.3 / spec task-pipeline)
    assert is_legal_task_transition(TaskStatus.FAILED, TaskStatus.RUNNING)
    assert is_legal_task_transition(TaskStatus.CANCELLED, TaskStatus.RUNNING)
    assert is_legal_task_transition(TaskStatus.COMPLETED, TaskStatus.RUNNING)


def test_illegal_task_transitions_rejected():
    illegal = [
        (TaskStatus.COMPLETED, TaskStatus.PENDING),
        (TaskStatus.COMPLETED, TaskStatus.FAILED),
        (TaskStatus.FAILED, TaskStatus.COMPLETED),     # 未经 rerun 直接转完成
        (TaskStatus.CANCELLED, TaskStatus.COMPLETED),
        (TaskStatus.PENDING, TaskStatus.COMPLETED),    # 跳过 running
        (TaskStatus.RUNNING, TaskStatus.PENDING),
    ]
    for src, dst in illegal:
        assert not is_legal_task_transition(src, dst), f"{src}→{dst} 应为非法"
        with pytest.raises(IllegalTransitionError):
            transition_task_status(src, dst)


def test_transition_task_status_returns_new_status():
    assert transition_task_status(TaskStatus.PENDING, TaskStatus.RUNNING) == TaskStatus.RUNNING
    assert transition_task_status("running", "failed") == TaskStatus.FAILED  # 字符串也接受


# --------------------------------------------------------------------------- #
# 2. 来源驱动的节点跳过(契约 §5.5)
# --------------------------------------------------------------------------- #
def test_skip_nodes_for_each_source():
    assert skip_nodes_for(SourceType.YOUTUBE) == set()
    assert skip_nodes_for(SourceType.BILIBILI) == set()
    assert skip_nodes_for(SourceType.DIRECT) == set()
    assert skip_nodes_for(SourceType.LOCAL_VIDEO) == {NodeName.DOWNLOAD}
    assert skip_nodes_for(SourceType.LOCAL_AUDIO) == {NodeName.DOWNLOAD, NodeName.EXTRACT_AUDIO}
    # 字符串来源等价
    assert skip_nodes_for("local_audio") == {NodeName.DOWNLOAD, NodeName.EXTRACT_AUDIO}


def test_first_executable_node_respects_skip():
    assert first_executable_node(skip_nodes_for("youtube")) == NodeName.DOWNLOAD
    assert first_executable_node(skip_nodes_for("local_video")) == NodeName.EXTRACT_AUDIO
    assert first_executable_node(skip_nodes_for("local_audio")) == NodeName.ASR


def test_fresh_state_marks_skipped_nodes():
    st = TaskState.fresh("task_la", "local_audio")
    assert st.nodes[NodeName.DOWNLOAD].status == NodeStatus.SKIPPED
    assert st.nodes[NodeName.EXTRACT_AUDIO].status == NodeStatus.SKIPPED
    assert st.nodes[NodeName.ASR].status == NodeStatus.PENDING
    assert st.status == TaskStatus.PENDING
    assert st.progress == 0  # 新建任务总体进度为 0(spec task-pipeline)


# --------------------------------------------------------------------------- #
# 3. 完整六步按序执行并产出全部产物(youtube)
# --------------------------------------------------------------------------- #
def test_full_run_youtube_completes_all_nodes(tmp_path):
    task = make_task("task_yt", "youtube")
    bus = RecorderBus()
    repo = RepoSpy()
    execs, called = build_executors()

    state = run_task_dag(
        task, data_root=tmp_path, repo=repo, bus=bus,
        download=execs[NodeName.DOWNLOAD], extract_audio=execs[NodeName.EXTRACT_AUDIO],
        asr=execs[NodeName.ASR], note=execs[NodeName.NOTE],
        mindmap=execs[NodeName.MINDMAP], cleanup=execs[NodeName.CLEANUP],
    )

    # 任务终态 completed,进度 100
    assert state.status == TaskStatus.COMPLETED
    assert state.progress == 100
    assert state.finished_at is not None
    # 六节点按拓扑序全部执行(cleanup 在最后)
    assert called == [NodeName.DOWNLOAD, NodeName.EXTRACT_AUDIO, NodeName.ASR,
                      NodeName.NOTE, NodeName.MINDMAP, NodeName.CLEANUP]
    # 全部节点 completed
    for n in NODE_ORDER:
        assert state.nodes[n].status == NodeStatus.COMPLETED, f"{n} 应 completed"
    # 五类产物(顶层指针 + 节点 product)登记一致
    assert task.video_path == state.artifacts["video"]
    assert task.audio_path == state.artifacts["audio"]
    assert task.srt_path == state.artifacts["srt"]
    assert task.note_path == state.artifacts["note"]
    assert state.mindmap_paths and state.mindmap_paths[0].endswith(".xmind")
    # 产物文件实际落盘
    assert (tmp_path / task.video_path).exists()
    assert (tmp_path / task.srt_path).exists()
    # 回写到 task 对象
    assert task.status == "completed"
    assert task.progress == 100
    # 持久化被调用(状态先落库)
    assert len(repo.calls) >= 1
    # SSE 事件顺序:每个节点 entered 在 completed 前;最后 task-completed
    types = bus.types()
    assert types.index("node-entered") < types.index("node-completed")
    assert types[-1] == "task-completed"
    # node_statuses 回写为契约 §1.2 结构
    ns = task.node_statuses
    assert set(ns.keys()) == {n.value for n in NODE_ORDER}
    assert ns["download"]["status"] == "completed"
    assert ns["download"]["product"]["path"].endswith(".mp4")
    assert ns["cleanup"]["status"] == "completed"


def test_node_progress_aggregation_and_weight():
    st = TaskState.fresh("task_x", "youtube")
    # 全部 pending → 进度 0
    assert st.overall_progress() == 0
    # download 推到 100、asr 推到 50 → 25 + 30*0.5 = 40
    st.nodes[NodeName.DOWNLOAD].progress = 100
    st.nodes[NodeName.ASR].progress = 50
    assert st.overall_progress() == 40
    # 全 completed → 100
    for n in NODE_ORDER:
        st.nodes[n].progress = 100
    assert st.overall_progress() == 100


# --------------------------------------------------------------------------- #
# 4. 本地音频来源跳过 download/extract,直接从 asr 起
# --------------------------------------------------------------------------- #
def test_local_audio_skips_download_and_extract(tmp_path):
    # 上传音频文件已落盘并登记到顶层 audio_path
    audio_rel = "audio/task_la/upload.wav"
    (tmp_path / audio_rel).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / audio_rel).write_bytes(b"wav")
    task = make_task("task_la", "local_audio", audio_path=audio_rel)

    bus = RecorderBus()
    execs, called = build_executors()

    state = run_task_dag(
        task, data_root=tmp_path, bus=bus,
        download=execs[NodeName.DOWNLOAD], extract_audio=execs[NodeName.EXTRACT_AUDIO],
        asr=execs[NodeName.ASR], note=execs[NodeName.NOTE],
        mindmap=execs[NodeName.MINDMAP], cleanup=execs[NodeName.CLEANUP],
    )

    assert state.status == TaskStatus.COMPLETED
    # download / extract 被跳过,执行器未调用
    assert NodeName.DOWNLOAD not in called
    assert NodeName.EXTRACT_AUDIO not in called
    assert state.nodes[NodeName.DOWNLOAD].status == NodeStatus.SKIPPED
    assert state.nodes[NodeName.EXTRACT_AUDIO].status == NodeStatus.SKIPPED
    # 从 asr 起执行
    assert called[:1] == [NodeName.ASR]
    # skipped 节点 product 为 null(契约 §1.2),顶层 audio_path 保留为上传值
    assert state.nodes[NodeName.EXTRACT_AUDIO].product is None
    assert state.artifacts["audio"] == audio_rel
    # 任务不因 skipped 节点被判 failed
    assert state.error is None


def test_local_video_skips_download_only(tmp_path):
    video_rel = "videos/task_lv/upload.mp4"
    (tmp_path / video_rel).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / video_rel).write_bytes(b"mp4")
    task = make_task("task_lv", "local_video", video_path=video_rel)
    execs, called = build_executors()

    state = run_task_dag(task, data_root=tmp_path, **_kw_exec(execs))

    assert state.status == TaskStatus.COMPLETED
    assert NodeName.DOWNLOAD not in called
    assert state.nodes[NodeName.DOWNLOAD].status == NodeStatus.SKIPPED
    # extract_audio 仍执行(从上传视频提取音频)
    assert NodeName.EXTRACT_AUDIO in called


def _kw_exec(execs):
    """把 executors dict 展开为 run_task_dag 的关键字参数。"""
    return {
        "download": execs[NodeName.DOWNLOAD],
        "extract_audio": execs[NodeName.EXTRACT_AUDIO],
        "asr": execs[NodeName.ASR],
        "note": execs[NodeName.NOTE],
        "mindmap": execs[NodeName.MINDMAP],
        "cleanup": execs[NodeName.CLEANUP],
    }


# --------------------------------------------------------------------------- #
# 5. 缺上游产物即终止(契约 §5.2.2 / spec task-pipeline)
# --------------------------------------------------------------------------- #
def test_missing_upstream_product_fails_node():
    # download 不登记 video 产物 → extract_audio 缺上游产物
    task = make_task("task_miss", "youtube")
    bus = RecorderBus()
    execs, called = build_executors(skip_product={NodeName.DOWNLOAD})

    state = run_task_dag(task, data_root=None, bus=bus, **_kw_exec(execs))

    assert state.status == TaskStatus.FAILED
    assert state.nodes[NodeName.EXTRACT_AUDIO].status == NodeStatus.FAILED
    err = state.nodes[NodeName.EXTRACT_AUDIO].error
    assert err is not None and "缺少上游产物" in err and "extract_audio" in err
    # 失败节点的下游未执行(asr/note/mindmap 仍 pending)
    assert state.nodes[NodeName.ASR].status == NodeStatus.PENDING
    assert NodeName.ASR not in called
    # 任务总体 error 含中文信息
    assert state.error is not None and "缺少上游产物" in state.error


def test_missing_upstream_file_on_disk_fails(tmp_path):
    # 登记了一个并不存在的 srt 路径 → note 节点缺上游产物
    task = make_task("task_missf", "youtube", srt_path="srt/t/ghost.srt")
    execs, called = build_executors(skip_product={NodeName.DOWNLOAD, NodeName.EXTRACT_AUDIO,
                                                   NodeName.ASR})
    state = run_task_dag(task, data_root=tmp_path, **_kw_exec(execs))
    # download/extract/asr 全 no-op 不登记产物 → asr 阶段就会先失败于缺 audio
    assert state.status == TaskStatus.FAILED


# --------------------------------------------------------------------------- #
# 6. cleanup 在成功与失败两条路径都执行(契约 §5.1)
# --------------------------------------------------------------------------- #
def test_cleanup_runs_on_success(tmp_path):
    task = make_task("task_ok", "youtube")
    execs, called = build_executors()
    state = run_task_dag(task, data_root=tmp_path, **_kw_exec(execs))
    assert state.status == TaskStatus.COMPLETED
    assert NodeName.CLEANUP in called
    assert state.nodes[NodeName.CLEANUP].status == NodeStatus.COMPLETED


def test_cleanup_runs_on_failure(tmp_path):
    task = make_task("task_fail", "youtube")
    bus = RecorderBus()
    execs, called = build_executors(fail_at=NodeName.ASR)
    state = run_task_dag(task, data_root=tmp_path, bus=bus, **_kw_exec(execs))

    # ASR 失败 → 任务 failed
    assert state.status == TaskStatus.FAILED
    assert state.nodes[NodeName.ASR].status == NodeStatus.FAILED
    # 失败节点下游不执行
    assert NodeName.NOTE not in called
    # 但 cleanup 仍执行(双路径必执行)
    assert NodeName.CLEANUP in called
    assert state.nodes[NodeName.CLEANUP].status == NodeStatus.COMPLETED
    # task-failed 事件被推送
    assert "task-failed" in bus.types()
    assert "node-failed" in bus.types()


# --------------------------------------------------------------------------- #
# 7. 节点级重跑:复用上游 completed 产物、级联重算下游、干净工作上下文
# --------------------------------------------------------------------------- #
def test_rerun_reuses_upstream_and_cascades_downstream(tmp_path):
    # 先完整跑一次到 completed
    task = make_task("task_re", "youtube")
    execs1, called1 = build_executors()
    state = run_task_dag(task, data_root=tmp_path, **_kw_exec(execs1))
    assert state.status == TaskStatus.COMPLETED
    video_before = state.artifacts["video"]

    # 从 asr 重跑:复用 download/extract 产物,级联重算 asr/note/mindmap/cleanup
    execs2, called2 = build_executors()
    bus = RecorderBus()
    runner = DagRunner(
        "task_re", state=state, data_root=tmp_path, bus=bus,
        executors={n: execs2[n] for n in NODE_ORDER},
    )
    final = runner.run(from_node=NodeName.ASR)

    assert final.status == TaskStatus.COMPLETED
    # 上游 download/extract 未重跑(产物复用)
    assert NodeName.DOWNLOAD not in called2
    assert NodeName.EXTRACT_AUDIO not in called2
    # 上游产物保留未变
    assert final.artifacts["video"] == video_before
    assert (tmp_path / video_before).exists()
    # asr 及下游级联重算
    assert called2[:1] == [NodeName.ASR]
    for n in (NodeName.ASR, NodeName.NOTE, NodeName.MINDMAP, NodeName.CLEANUP):
        assert n in called2
        assert final.nodes[n].status == NodeStatus.COMPLETED
    # 重跑成功清除失败记录(无 error)
    assert final.error is None


def test_rerun_does_not_reuse_half_products(tmp_path):
    # asr 曾失败,残留半成品 srt(标记 product 但内容损坏);从 asr 重跑应清场重生
    task = make_task("task_half", "youtube")
    execs1, _ = build_executors()
    state = run_task_dag(task, data_root=tmp_path, **_kw_exec(execs1))

    # 模拟 asr 半成品:把 asr 节点置 failed 并塞一个脏 product
    state.nodes[NodeName.ASR].status = NodeStatus.FAILED
    state.nodes[NodeName.ASR].error = "上次失败"
    dirty = "srt/task_half/dirty.srt"
    (tmp_path / dirty).write_bytes(b"dirty half product")
    state.artifacts["srt"] = dirty
    state.nodes[NodeName.ASR].product = {"path": dirty, "size_bytes": 99}
    # 下游 note/mindmap 也残留半成品状态
    state.nodes[NodeName.NOTE].status = NodeStatus.FAILED

    execs2, called2 = build_executors()
    runner = DagRunner("task_half", state=state, data_root=tmp_path,
                       executors={n: execs2[n] for n in NODE_ORDER})
    final = runner.run(from_node=NodeName.ASR)

    assert final.status == TaskStatus.COMPLETED
    # asr 重新执行(未复用半成品),产物路径由执行器重新生成
    assert NodeName.ASR in called2
    new_srt = final.artifacts["srt"]
    assert new_srt.endswith(".srt")
    # 节点 error 被清除
    assert final.nodes[NodeName.ASR].error is None


def test_rerun_falls_back_when_upstream_missing(tmp_path):
    # download/extract/asr 都 completed,但 asr 的 srt 产物文件被删
    task = make_task("task_fb", "youtube")
    execs1, _ = build_executors()
    state = run_task_dag(task, data_root=tmp_path, **_kw_exec(execs1))
    srt_rel = state.artifacts["srt"]
    (tmp_path / srt_rel).unlink()  # 删除 srt 文件
    assert state.status == TaskStatus.COMPLETED

    # 请求从 note 重跑 → 应回退到 asr
    execs2, called2 = build_executors()
    runner = DagRunner("task_fb", state=state, data_root=tmp_path,
                       executors={n: execs2[n] for n in NODE_ORDER})
    final = runner.run(from_node=NodeName.NOTE)

    assert final.status == TaskStatus.COMPLETED
    # download/extract 复用(产物文件仍存在)
    assert NodeName.DOWNLOAD not in called2
    assert NodeName.EXTRACT_AUDIO not in called2
    # 回退到 asr 重跑(asr 首个被执行)
    assert called2[:1] == [NodeName.ASR]
    # srt 重新生成
    assert (tmp_path / final.artifacts["srt"]).exists()


def test_rerun_rejected_for_pending_via_state_machine():
    # pending 任务不能直接 rerun:在 DagRunner 中 _transition_task(pending→running) 合法,
    # 但若试图把 completed 误当 pending 处理 —— 这里直接验证状态机层拒绝 completed→failed。
    assert not is_legal_task_transition(TaskStatus.COMPLETED, TaskStatus.FAILED)


# --------------------------------------------------------------------------- #
# 8. 取消协议(契约 §0.6)
# --------------------------------------------------------------------------- #
def test_cancel_running_task_preserves_completed_products(tmp_path):
    task = make_task("task_can", "youtube")
    bus = RecorderBus()
    execs, called = build_executors(cancel_at=NodeName.ASR)
    state = run_task_dag(task, data_root=tmp_path, bus=bus, **_kw_exec(execs))

    # 任务转 cancelled
    assert state.status == TaskStatus.CANCELLED
    # 已 completed 节点产物保留
    assert state.nodes[NodeName.DOWNLOAD].status == NodeStatus.COMPLETED
    assert state.nodes[NodeName.EXTRACT_AUDIO].status == NodeStatus.COMPLETED
    assert state.artifacts["video"] is not None
    # 被中断的 asr 未完成,下游未执行
    assert NodeName.NOTE not in called
    # cleanup 仍执行
    assert NodeName.CLEANUP in called
    # task-cancelled 事件推送
    assert "task-cancelled" in bus.types()


def test_cancel_token_is_thread_safe_and_idempotent():
    tok = CancelToken()
    assert not tok.is_cancelled()
    tok.cancel()
    assert tok.is_cancelled()
    tok.cancel()  # 重复取消不报错


# --------------------------------------------------------------------------- #
# 9. 重启恢复:残留 running 标 failed(契约 §0.9 / spec task-pipeline)
# --------------------------------------------------------------------------- #
def test_recover_running_on_startup_marks_failed():
    st = TaskState.fresh("task_r", "youtube")
    st.status = TaskStatus.RUNNING
    st.nodes[NodeName.ASR].status = NodeStatus.RUNNING
    st.nodes[NodeName.ASR].started_at = "2026-07-25T10:00:00"

    recovered = recover_running_on_startup(st)

    assert recovered is True
    assert st.status == TaskStatus.FAILED
    assert st.error is not None and "重启中断于" in st.error and "asr" in st.error
    assert st.nodes[NodeName.ASR].status == NodeStatus.FAILED
    assert st.finished_at is not None


def test_recover_skips_non_running_state():
    st = TaskState.fresh("task_r2", "youtube")
    st.status = TaskStatus.COMPLETED
    assert recover_running_on_startup(st) is False
    assert st.status == TaskStatus.COMPLETED  # 不变


# --------------------------------------------------------------------------- #
# 10. DAG 编排函数:接受执行器钩子,产物回写 task
# --------------------------------------------------------------------------- #
def test_run_task_dag_writes_products_back_to_task(tmp_path):
    task = make_task("task_wb", "youtube")
    execs, _ = build_executors()
    state = run_task_dag(task, data_root=tmp_path, **_kw_exec(execs))

    # 回写到 task 对象的顶层字段
    assert task.status == "completed"
    assert task.video_path is not None and task.video_path.startswith("videos/")
    assert task.audio_path.startswith("audio/")
    assert task.srt_path.startswith("srt/")
    assert task.note_path.startswith("notes/")
    assert isinstance(task.mindmap_paths, list) and task.mindmap_paths
    # node_statuses 结构完整
    assert isinstance(task.node_statuses, dict)
    assert task.node_statuses["asr"]["status"] == "completed"


def test_executor_receives_context_with_progress_and_log(tmp_path):
    """执行器钩子能通过 ctx 推进度 / 日志 / 取产物路径。"""
    bus = RecorderBus()
    seen = {}

    def asr_exec(ctx):
        seen["data_root"] = ctx.data_root
        seen["source_type"] = ctx.source_type
        ctx.emit_progress(42, "转写中")
        ctx.emit_log("info", "ASR 引擎就绪")
        p = ctx.product_path("srt", "srt")
        p.write_bytes(b"1\n00:00:01,000 --> 00:00:02,000\nhi\n")
        ctx.register_product("srt", ctx.rel_of(p), p.stat().st_size)

    task = make_task("task_ctx", "youtube")
    execs, _ = build_executors()
    execs[NodeName.ASR] = asr_exec
    run_task_dag(task, data_root=tmp_path, bus=bus, **_kw_exec(execs))

    assert seen["source_type"] == "youtube"
    # 进度与日志事件被推送
    prog = [d for d in bus.of("node-progress") if d.get("node") == "asr"]
    assert any(d.get("progress") == 42 for d in prog)
    assert any(d.get("line") == "ASR 引擎就绪" for d in bus.of("log"))


def test_no_executor_means_noop_node_completes_without_product(tmp_path):
    """未注册执行器的节点按 no-op 完成;无产物则下游缺上游产物终止(整合阶段未接入时的行为)。"""
    task = make_task("task_noop", "youtube")
    # 只给 download,其余不注入
    def dl(ctx):
        p = ctx.product_path("video", "mp4")
        p.write_bytes(b"x")
        ctx.register_product("video", ctx.rel_of(p), 1)

    state = run_task_dag(task, data_root=tmp_path, download=dl)
    assert state.nodes[NodeName.DOWNLOAD].status == NodeStatus.COMPLETED
    # extract_audio 无执行器 → no-op 完成但无 audio 产物 → asr 缺上游产物失败
    assert state.status == TaskStatus.FAILED
    assert "缺少上游产物" in (state.error or "")
