"""
六步 DAG 编排器(设计 D8 / 规格 task-pipeline / 契约 §5 §6.6)
=============================================================

本模块实现六节点流水线 DAG 的**运行时模型**与**编排器**:

- :class:`NodeState` / :class:`TaskState`:六节点状态机 + 总体状态的运行时权威视图
  (镜像 ``Task.node_statuses`` + 顶层产物指针),解耦于真实 Task / Repository,
  便于在 Task 模型与 SSE 层尚未改造完成时独立单测编排逻辑。
- :class:`NodeContext`:节点执行器与框架之间的桥接(产物路径 / 产物登记 /
  进度日志推送 / 取消信号),即契约 §6 的「通用回调类型」。
- :class:`DagRunner`:按拓扑序推进状态机;按来源跳过;缺上游产物终止;
  节点级重跑;清理节点在成功与失败两条路径都执行;取消协议;「状态先落库再推」。
- :func:`run_task_dag`:功能糖,接受各步骤可调用执行器(下载/提取音频/ASR/笔记/
  思维导图/清理)并驱动 :class:`DagRunner`,产物回写 task。

**整合阶段接入点**:各节点的具体执行逻辑以**可调用执行器钩子**注入
(``executors: NodeName → Callable[[NodeContext], None]``);本阶段先把框架与状态机
做扎实,钩子内留待整合阶段接入 ``media_ingest`` / ``speech_to_text`` /
``note_generation`` / ``mindmap`` / ``retention`` 等真实模块。

内核边界(契约 §0.2):``logger`` 经 ``from src.core.kernel import`` 取;内核未就绪时
降级为标准 logging,使本模块在纯单测环境亦可导入运行。
"""
from __future__ import annotations

import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from .states import (
    ARTIFACT_TASK_FIELD,
    NODE_ORDER,
    NODE_WEIGHTS,
    REQUIRED_ARTIFACT,
    IllegalTransitionError,
    NodeName,
    NodeStatus,
    TaskStatus,
    _coerce_node,
    _coerce_source,
    _coerce_task_status,
    is_legal_task_transition,
    nodes_before,
    nodes_from,
    skip_nodes_for,
    transition_task_status,
)

# 内核 logger:优先从内核门面取;内核未就绪时降级为标准 logging(单测环境可用)。
try:  # pragma: no cover - 分支取决于内核是否就绪
    from src.core.kernel import logger  # type: ignore
except Exception:  # noqa: BLE001 - 内核缺失时降级,不阻断编排层
    import logging

    logger = logging.getLogger("pipeline.dag")


# --------------------------------------------------------------------------- #
# 产物类别 ↔ 产出节点
# --------------------------------------------------------------------------- #
# 产物类别 → 产出该产物的节点(用于登记时同步 node product,以及重跑清场时定位)。
_PRODUCER_NODE: dict[str, NodeName] = {
    "video": NodeName.DOWNLOAD,
    "audio": NodeName.EXTRACT_AUDIO,
    "srt": NodeName.ASR,
    "note": NodeName.NOTE,
}
# 逆映射:节点 → 其单一主产物类别(mindmap 多格式、cleanup 无产物,不在此表)。
_PRODUCER_BY_NODE: dict[NodeName, str] = {v: k for k, v in _PRODUCER_NODE.items()}

# 各产物类别落盘的默认文件名基(扩展名由执行器指定)。
_PRODUCT_BASE: dict[str, str] = {
    "video": "clip",
    "audio": "audio",
    "srt": "subtitle",
    "note": "note",
    "screenshot": "shot",
    "mindmap": "mindmap",
}

# 产物类别 → 落盘目录名(契约 §2.1:目录名非统一复数;audio/srt 单数,mindmap 与 note 同放 notes/)。
_KIND_DIR: dict[str, str] = {
    "video": "videos",
    "audio": "audio",
    "srt": "srt",
    "note": "notes",
    "screenshot": "screenshots",
    "mindmap": "notes",
}


# --------------------------------------------------------------------------- #
# 运行时状态模型
# --------------------------------------------------------------------------- #
@dataclass
class NodeState:
    """单节点的运行时状态(镜像 ``node_statuses[<node>]``,契约 §1.2)。"""

    status: NodeStatus = NodeStatus.PENDING
    progress: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    product: Optional[dict] = None  # {"path": <rel>, "size_bytes": <int>} 或 None

    def to_dict(self) -> dict:
        """序列化为可落库的 JSON 兼容字典(契约 §1.2 结构)。"""
        return {
            "status": self.status.value if isinstance(self.status, NodeStatus) else str(self.status),
            "progress": int(self.progress or 0),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "product": self.product,
        }

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "NodeState":
        """从持久化的字典(或 None)反序列化;缺字段回落默认值。"""
        d = d or {}
        try:
            status = _coerce_node_status(d.get("status", NodeStatus.PENDING))
        except ValueError:
            status = NodeStatus.PENDING
        return cls(
            status=status,
            progress=int(d.get("progress", 0) or 0),
            started_at=d.get("started_at"),
            finished_at=d.get("finished_at"),
            error=d.get("error"),
            product=d.get("product"),
        )


def _coerce_node_status(value: Any) -> NodeStatus:
    if isinstance(value, NodeStatus):
        return value
    if value is None:
        return NodeStatus.PENDING
    return NodeStatus(str(value))


@dataclass
class TaskState:
    """六节点 DAG 的运行时权威视图。

    解耦层:本对象在内存中持有六节点状态机 + 总体状态 + 各产物顶层指针,既可从真实
    v1 ``Task`` 对象(``Task.node_statuses`` / ``Task.source_type`` / ``Task.video_path`` ...)
    加载,也可在 Task 模型尚未改造完成时从纯字典 / 桩构造,使 DAG 编排可独立单测。

    顶层指针(``artifacts``:video / audio / srt / note)与产出节点 ``product.path``
    保持同步(契约 §1.2),作为下游节点「缺上游产物」检查的依据。
    """

    task_id: str
    source_type: str
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    nodes: dict[NodeName, NodeState] = field(default_factory=dict)
    error: Optional[str] = None
    finished_at: Optional[str] = None
    # 顶层产物便捷指针(相对 DATA_ROOT 的 POSIX 路径):kind → rel_path
    artifacts: dict[str, str] = field(default_factory=dict)
    # 多产物(note 节点的 screenshots、mindmap 节点的多格式导出)
    screenshot_paths: list[str] = field(default_factory=list)
    mindmap_paths: list[str] = field(default_factory=list)

    @classmethod
    def fresh(
        cls,
        task_id: str,
        source_type: "str | SourceType",
        skip: Optional[set[NodeName]] = None,
    ) -> "TaskState":
        """构造初始 TaskState:总体 pending、各节点 pending(被跳过节点置 skipped)。

        Args:
            task_id: 任务 ID。
            source_type: 媒体来源类型;跳过集合默认由 :func:`skip_nodes_for` 推导。
            skip: 显式跳过集合(覆盖来源推导,主要供测试与重跑)。
        """
        state = cls(task_id=task_id, source_type=_coerce_source(source_type).value)
        skip_set = skip if skip is not None else skip_nodes_for(source_type)
        for n in NODE_ORDER:
            state.nodes[n] = NodeState(
                status=NodeStatus.SKIPPED if n in skip_set else NodeStatus.PENDING
            )
        return state

    # ----- 查询 -----
    def skip_set(self) -> set[NodeName]:
        """返回当前被标记为 skipped 的节点集合。"""
        return {n for n in NODE_ORDER if self.nodes[n].status == NodeStatus.SKIPPED}

    def artifact(self, kind: str) -> Optional[str]:
        """返回某类别产物的顶层相对路径(未登记返回 None)。"""
        return self.artifacts.get(kind)

    def completed(self, node: "NodeName | str") -> bool:
        return self.nodes[_coerce_node(node)].status == NodeStatus.COMPLETED

    def running_node(self) -> Optional[NodeName]:
        """返回当前处于 running 的节点(无则 None);用于重启恢复定位中断点。"""
        for n in NODE_ORDER:
            if self.nodes[n].status == NodeStatus.RUNNING:
                return n
        return None

    def overall_progress(self) -> int:
        """总体进度 = 六节点进度的加权聚合(skipped 按 100 计,cleanup 权重较小)。

        契约 §5.4:返回 0–100 整数。
        """
        total = 0
        for n in NODE_ORDER:
            ns = self.nodes[n]
            if ns.status == NodeStatus.SKIPPED:
                total += NODE_WEIGHTS[n]  # skipped 节点按 100% 计入
            else:
                total += NODE_WEIGHTS[n] * max(0, min(100, int(ns.progress or 0))) // 100
        return max(0, min(100, total))

    # ----- 写入 -----
    def set_artifact(
        self, kind: str, rel_path: str, size_bytes: int = 0
    ) -> None:
        """登记产物顶层指针,并同步产出节点的 product(契约 §1.2 双写)。"""
        self.artifacts[kind] = rel_path
        producer = _PRODUCER_NODE.get(kind)
        if producer is not None:
            self.nodes[producer].product = {
                "path": rel_path,
                "size_bytes": int(size_bytes or 0),
            }

    def reset_node(self, node: "NodeName | str") -> None:
        """重置节点为 pending 并清空其产物(保留 skipped 语义不被破坏)。"""
        n = _coerce_node(node)
        ns = self.nodes[n]
        if ns.status == NodeStatus.SKIPPED:
            return  # 跳过节点不参与重跑清场
        kind = _PRODUCER_BY_NODE.get(n)
        if kind:
            self.artifacts.pop(kind, None)
        if n == NodeName.NOTE:
            self.screenshot_paths.clear()
        if n == NodeName.MINDMAP:
            self.mindmap_paths.clear()
        ns.product = None
        ns.status = NodeStatus.PENDING
        ns.progress = 0
        ns.started_at = None
        ns.finished_at = None
        ns.error = None

    # ----- 序列化 -----
    def to_node_statuses_dict(self) -> dict:
        """导出为 ``node_statuses`` JSON 结构(契约 §1.2)。"""
        return {n.value: self.nodes[n].to_dict() for n in NODE_ORDER}


# --------------------------------------------------------------------------- #
# 取消信号
# --------------------------------------------------------------------------- #
class CancelToken:
    """任务级取消信号(契约 §0.6 取消协议)。

    DAG 向每个运行节点注入本令牌;节点执行体周期性调用 :meth:`is_cancelled`,
    被取消时尽快抛 :class:`PipelineCancelled`,**丢弃**本节点半成品、**保留**已
    completed 节点产物。底层用 :class:`threading.Event`,线程安全。
    """

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()


class PipelineCancelled(Exception):
    """节点执行被取消时抛出(DAG 捕获后把任务转为 cancelled 终态)。"""


# 节点执行器钩子类型:接收 NodeContext,通过 ctx 登记产物 / 推进度日志 / 检查取消。
NodeExecutor = Callable[["NodeContext"], None]


# --------------------------------------------------------------------------- #
# NodeContext:执行器 ↔ 框架的桥接(契约 §6 通用回调)
# --------------------------------------------------------------------------- #
class NodeContext:
    """节点执行器与 DAG 框架之间的桥接(契约 §6「通用回调类型」)。

    每个节点开始时由 :class:`DagRunner` 构造一个 ``NodeContext`` 注入执行器钩子。
    执行器通过本对象:

    - :meth:`product_path` 取产物落盘绝对路径(自动创建父目录);
    - :meth:`register_product` 登记产物(写顶层指针 + 节点 product,先落库再推事件);
    - :meth:`emit_progress` / :meth:`emit_log` 推送进度与日志;
    - ``ctx.cancel.is_cancelled()`` 检查取消(契约 §0.6);
    - ``ctx.task`` / ``ctx.settings`` 读取任务快照与配置快照。

    本阶段 ``repo`` / ``bus`` 为可选注入(便于无基础设施时单测)。
    """

    def __init__(
        self,
        *,
        task_id: str,
        node: NodeName,
        state: TaskState,
        data_root: Optional[Path] = None,
        repo: Any = None,
        bus: Any = None,
        cancel: Optional[CancelToken] = None,
        settings: Any = None,
        task: Any = None,
    ) -> None:
        self.task_id = task_id
        self.node = node
        self._state = state
        self._data_root = Path(data_root) if data_root else Path("data")
        self._repo = repo
        self._bus = bus
        self.cancel = cancel or CancelToken()
        self.settings = settings
        self._task = task

    # ----- 任务快照 -----
    @property
    def task(self) -> Any:
        return self._task

    @property
    def data_root(self) -> Path:
        """DATA_ROOT 绝对路径(产物落盘与缺产物校验的基准)。"""
        return self._data_root

    @property
    def source_type(self) -> str:
        return self._state.source_type

    def rel_of(self, abs_path: "str | Path") -> str:
        """把绝对路径转为相对 DATA_ROOT 的 POSIX 相对路径(契约 §0.4 落库约定)。

        不在 DATA_ROOT 之下时原样返回字符串。
        """
        try:
            return Path(abs_path).relative_to(self._data_root).as_posix()
        except ValueError:
            return str(abs_path)

    # ----- 产物 -----
    def product_path(self, kind: str, ext: str) -> Path:
        """返回 ``<DATA_ROOT>/<dir>/<task_id>/<base>.<ext>`` 绝对路径并确保父目录存在。

        契约 §6 / §2.1:按类型分目录(目录名见 :data:`_KIND_DIR`)、按 task_id 二级隔离。
        """
        d = self._data_root / _KIND_DIR.get(kind, f"{kind}s") / self.task_id
        d.mkdir(parents=True, exist_ok=True)
        base = _PRODUCT_BASE.get(kind, kind)
        return d / f"{base}.{ext.lstrip('.')}"

    def register_product(self, kind: str, rel_path: str, size_bytes: int = 0) -> None:
        """登记节点产物:写顶层 ``artifacts`` 指针 + 产出节点 ``product``,
        多产物类别(screenshot / mindmap)追加到列表,随后「先落库再推事件」。"""
        self._state.set_artifact(kind, rel_path, size_bytes)
        if kind == "screenshot" and rel_path not in self._state.screenshot_paths:
            self._state.screenshot_paths.append(rel_path)
        elif kind == "mindmap" and rel_path not in self._state.mindmap_paths:
            self._state.mindmap_paths.append(rel_path)
        _try_persist(self._repo, self.task_id, self._state)
        _try_publish(
            self._bus,
            self.task_id,
            "node-product",
            {"node": self.node.value, "kind": kind, "path": rel_path, "size_bytes": int(size_bytes or 0)},
        )

    # ----- 进度 / 日志 -----
    def emit_progress(self, percent: int, message: Optional[str] = None) -> None:
        """推送节点进度(先落库 ``node_statuses[node].progress`` 再推 ``node-progress``)。"""
        p = max(0, min(100, int(percent)))
        self._state.nodes[self.node].progress = p
        self._state.progress = self._state.overall_progress()
        _try_persist(self._repo, self.task_id, self._state)
        _try_publish(
            self._bus,
            self.task_id,
            "node-progress",
            {"node": self.node.value, "progress": p, "message": message},
        )

    def emit_log(self, level: str, line: str) -> None:
        """推送日志行(level ∈ info/ok/warn/error);近实时逐行(spec SSE「实时日志」)。"""
        _try_publish(self._bus, self.task_id, "log", {"level": level, "line": line})


# --------------------------------------------------------------------------- #
# 持久化 / 推送的小工具(鸭子类型,容错)
# --------------------------------------------------------------------------- #
def _try_persist(repo: Any, task_id: str, state: TaskState) -> None:
    """把 TaskState 落库;repo 为 None 或方法不可用时静默降级(框架阶段默认内存态)。

    期望的 repo 钩子签名(整合阶段由 TaskRepository 适配器提供):
    ``repo.update_task_state(task_id: str, state: TaskState) -> None``。
    """
    if repo is None:
        return
    try:
        repo.update_task_state(task_id, state)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - 持久化失败不得阻断编排
        logger.debug("持久化任务状态失败 task=%s", task_id, exc_info=True)


def _try_publish(bus: Any, task_id: str, event_type: str, data: dict) -> None:
    """向 EventBus 推事件;bus 为 None 或方法不可用时静默降级。

    期望的 bus 钩子签名(契约 §6.8 EventBus):
    ``bus.publish(task_id: str, event_type: str, data: dict) -> None``。
    """
    if bus is None:
        return
    try:
        bus.publish(task_id, event_type, data)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - 推送失败不得阻断编排
        logger.debug("推送事件失败 task=%s event=%s", task_id, event_type, exc_info=True)


# --------------------------------------------------------------------------- #
# DagRunner:六步 DAG 编排器
# --------------------------------------------------------------------------- #
class DagRunner:
    """六步 DAG 编排器(设计 D8 / 规格 task-pipeline / 契约 §5 §6.6)。

    职责:按拓扑序推进六节点状态机;按来源跳过 download / extract_audio;
    节点缺上游产物即终止;节点级重跑(复用上游 completed 产物、级联重算下游、
    干净工作上下文不复用半成品);清理节点在成功与失败两条路径都执行;
    取消协议;「状态先落库再推 SSE」(契约 §0.5)。

    各节点具体执行逻辑以**可调用执行器钩子**注入(``executors``);本阶段先把框架
    与状态机做扎实,钩子内留待整合阶段接入真实模块(见模块 docstring)。
    """

    def __init__(
        self,
        task_id: str,
        *,
        state: TaskState,
        repo: Any = None,
        bus: Any = None,
        settings: Any = None,
        data_root: "str | Path | None" = None,
        executors: Optional[dict] = None,
        cancel: Optional[CancelToken] = None,
        clock: Callable[[], datetime] = datetime.now,
        task: Any = None,
    ) -> None:
        if state is None:
            raise ValueError("DagRunner 必须传入初始 state(经 run_task_dag 或显式构造)")
        self.task_id = task_id
        self.state = state
        self.repo = repo
        self.bus = bus
        self.settings = settings
        self.data_root = Path(data_root) if data_root else None
        self.clock = clock
        self.cancel = cancel or CancelToken()
        self._task = task
        # 归一化执行器表:NodeName → callable
        self.executors: dict[NodeName, NodeExecutor] = {}
        for k, v in (executors or {}).items():
            self.executors[_coerce_node(k)] = v

    # ----------------------- 公共入口 ----------------------- #
    def run(self, from_node: "NodeName | str | None" = None) -> TaskState:
        """执行 DAG。

        - ``from_node=None``:从首个非 skipped 节点执行完整流水线(``pending → running``)。
        - ``from_node=<node>``:节点级重跑(契约 §5.3)——校验上游产物存在(缺失回退到
          缺失节点)、清空 from_node 及下游的工作上下文与半成品产物、复用上游 completed
          产物、级联重算至 cleanup。

        清理节点(cleanup)在 ``try/finally`` 中**必执行**,无论上游成败(契约 §5.1)。
        返回最终 :class:`TaskState`(调用方可据此回写真实 Task 对象)。
        """
        start_node = _coerce_node(from_node) if from_node is not None else None
        rerunning = start_node is not None

        if rerunning:
            start_node = self._prepare_rerun(start_node)
        else:
            self._transition_task(TaskStatus.RUNNING)

        failed_node: Optional[NodeName] = None
        cancelled = False

        try:
            for node in self._pipeline_iter(start_node):
                if self.state.nodes[node].status == NodeStatus.SKIPPED:
                    continue  # 来源驱动的跳过:保持 skipped 不执行
                if self.cancel.is_cancelled():
                    cancelled = True
                    break
                # 缺上游产物:立即失败终止(契约 §5.2.2 / spec task-pipeline)
                missing = self._check_upstream(node)
                if missing:
                    self._fail_node(node, missing)
                    failed_node = node
                    break
                # 进入节点:pending → running
                self._enter_node(node)
                if self.cancel.is_cancelled():
                    self._mark_cancelled_node(node)
                    cancelled = True
                    break
                # 执行节点钩子
                try:
                    executor = self.executors.get(node)
                    if executor is None:
                        logger.warning(
                            "节点 %s 未注册执行器(整合阶段接入真实模块),按 no-op 完成 task=%s",
                            node.value,
                            self.task_id,
                        )
                    else:
                        executor(self._make_ctx(node))
                except PipelineCancelled:
                    self._mark_cancelled_node(node)
                    cancelled = True
                    break
                except Exception as exc:  # noqa: BLE001 - 任意执行器异常都转为节点失败
                    self._fail_node(node, self._node_error(node, exc))
                    failed_node = node
                    break
                # 节点成功完成
                self._complete_node(node)
        finally:
            # cleanup 永不跳过:成功与失败两条路径都执行(契约 §5.1)
            self._run_cleanup()

        # 终态判定(cleanup 已执行完毕)
        if cancelled:
            self._finish(TaskStatus.CANCELLED, error="任务已取消")
        elif failed_node is not None:
            self._finish(
                TaskStatus.FAILED,
                error=self.state.nodes[failed_node].error,
                failed_node=failed_node,
            )
        else:
            self._finish(TaskStatus.COMPLETED)
        return self.state

    def request_cancel(self) -> None:
        """请求取消:置取消信号,运行中的节点在下一次检查时尽快停止(契约 §0.6)。"""
        self.cancel.cancel()

    # ----------------------- 内部:迭代范围 ----------------------- #
    def _pipeline_iter(self, start_node: Optional[NodeName]) -> list[NodeName]:
        """返回主循环要执行的节点(不含 cleanup —— cleanup 由 finally 独占)。"""
        nodes = [n for n in NODE_ORDER if n != NodeName.CLEANUP]
        if start_node is None:
            return nodes
        if start_node == NodeName.CLEANUP:
            return []  # 仅重跑 cleanup:主循环为空,只跑 finally 里的 cleanup
        return nodes[nodes.index(start_node) :]

    def _make_ctx(self, node: NodeName) -> NodeContext:
        return NodeContext(
            task_id=self.task_id,
            node=node,
            state=self.state,
            data_root=self.data_root,
            repo=self.repo,
            bus=self.bus,
            cancel=self.cancel,
            settings=self.settings,
            task=self._task,
        )

    # ----------------------- 内部:时间戳 / 推送 / 落库 ----------------------- #
    def _now_iso(self) -> str:
        return self.clock().isoformat()

    def _persist(self) -> None:
        _try_persist(self.repo, self.task_id, self.state)

    def _publish(self, event_type: str, data: dict) -> None:
        payload = {"ts": self._now_iso(), "task_id": self.task_id, **data}
        _try_publish(self.bus, self.task_id, event_type, payload)

    # ----------------------- 内部:节点生命周期 ----------------------- #
    def _apply_node_status(
        self,
        node: NodeName,
        status: NodeStatus,
        *,
        error: Optional[str] = None,
        progress: Optional[int] = None,
    ) -> None:
        ns = self.state.nodes[node]
        ns.status = status
        if error is not None:
            ns.error = error
        if status == NodeStatus.RUNNING and not ns.started_at:
            ns.started_at = self._now_iso()
        if status in (NodeStatus.COMPLETED, NodeStatus.FAILED):
            ns.finished_at = self._now_iso()
        if progress is not None:
            ns.progress = max(0, min(100, int(progress)))
        self.state.progress = self.state.overall_progress()
        self._persist()  # 状态先落库(契约 §0.5)

    def _enter_node(self, node: NodeName) -> None:
        self._apply_node_status(node, NodeStatus.RUNNING, progress=0)
        self._publish("node-entered", {"node": node.value})

    def _complete_node(self, node: NodeName) -> None:
        self._apply_node_status(node, NodeStatus.COMPLETED, progress=100)
        self._publish("node-completed", {"node": node.value, "progress": 100})

    def _fail_node(self, node: NodeName, error_zh: str) -> None:
        self._apply_node_status(
            node, NodeStatus.FAILED, error=error_zh, progress=self.state.nodes[node].progress
        )
        self._publish("node-failed", {"node": node.value, "error": error_zh})

    def _mark_cancelled_node(self, node: NodeName) -> None:
        # 节点级无 cancelled 枚举:记 failed + 「节点被取消」;任务终态由 cancelled 标志定。
        self._apply_node_status(
            node, NodeStatus.FAILED, error="节点被取消", progress=self.state.nodes[node].progress
        )

    def _node_error(self, node: NodeName, exc: BaseException) -> str:
        msg = str(exc).strip() or exc.__class__.__name__
        return f"{node.value} 节点失败:{msg}"

    def _check_upstream(self, node: NodeName) -> Optional[str]:
        """校验节点必需的上游产物存在;缺失返回中文错误,齐备返回 None。

        契约 §5.2.2:产物在 state 中未登记 **或** 文件已丢失均视为缺失。
        文件存在性校验仅在 ``data_root`` 已设置时进行(纯框架/单测模式可传 None 跳过)。
        """
        kind = REQUIRED_ARTIFACT.get(node)
        if kind is None:
            return None
        rel = self.state.artifact(kind)
        if not rel:
            return f"缺少上游产物:{node.value}"
        if self.data_root is not None and not (self.data_root / rel).exists():
            return f"缺少上游产物:{node.value}"
        return None

    # ----------------------- 内部:cleanup ----------------------- #
    def _run_cleanup(self) -> None:
        """执行 cleanup 节点(永不跳过;其自身失败不改变任务终态,仅记节点 failed)。"""
        node = NodeName.CLEANUP
        self._apply_node_status(node, NodeStatus.RUNNING, progress=0)
        self._publish("node-entered", {"node": node.value})
        try:
            executor = self.executors.get(node)
            if executor is None:
                logger.info(
                    "cleanup 未注册执行器(整合阶段接入 retention.cleanup_task_temp),按 no-op 完成 task=%s",
                    self.task_id,
                )
            else:
                executor(self._make_ctx(node))
        except Exception as exc:  # noqa: BLE001 - cleanup 失败不阻断终态
            err = self._node_error(node, exc)
            logger.error("cleanup 节点执行失败 task=%s: %s", self.task_id, err)
            self._apply_node_status(node, NodeStatus.FAILED, error=err)
            self._publish("node-failed", {"node": node.value, "error": err})
            return
        self._apply_node_status(node, NodeStatus.COMPLETED, progress=100)
        self._publish("node-completed", {"node": node.value, "progress": 100})

    # ----------------------- 内部:任务终态 ----------------------- #
    def _transition_task(self, dst: "TaskStatus | str") -> None:
        """任务总体状态迁移;非法迁移拒绝、保持原状态并记日志(规格 task-pipeline)。"""
        src = self.state.status
        try:
            self.state.status = transition_task_status(src, dst)
        except IllegalTransitionError:
            logger.warning(
                "非法任务状态迁移被拒绝 task=%s: %s → %s(状态保持不变)",
                self.task_id,
                src.value if isinstance(src, TaskStatus) else src,
                dst.value if isinstance(dst, TaskStatus) else dst,
            )

    def _finish(
        self,
        status: TaskStatus,
        *,
        error: Optional[str] = None,
        failed_node: Optional[NodeName] = None,
    ) -> None:
        self._transition_task(status)
        self.state.error = error
        self.state.progress = self.state.overall_progress()
        if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            self.state.finished_at = self._now_iso()
            # 重跑成功:清除失败记录(节点 error 归档清除,spec「重跑成功后清除失败记录」)
            if status == TaskStatus.COMPLETED:
                self._archive_node_errors()
        self._persist()
        event_type = {
            TaskStatus.COMPLETED: "task-completed",
            TaskStatus.FAILED: "task-failed",
            TaskStatus.CANCELLED: "task-cancelled",
        }[status]
        payload: dict = {"status": self.state.status.value, "progress": self.state.progress}
        if self.state.error:
            payload["error"] = self.state.error
        if failed_node is not None:
            payload["failed_node"] = failed_node.value
        self._publish(event_type, payload)

    def _archive_node_errors(self) -> None:
        """任务转 completed 时清除各节点的 error 字段(归档失败记录,spec task-pipeline)。"""
        for n in NODE_ORDER:
            if self.state.nodes[n].status == NodeStatus.FAILED:
                # completed 任务不应残留 failed 节点;保守置 pending 不会发生,这里仅清 error
                self.state.nodes[n].error = None

    # ----------------------- 内部:节点级重跑 ----------------------- #
    def _prepare_rerun(self, requested: NodeName) -> NodeName:
        """节点级重跑准备(契约 §5.3):

        1. 校验 ``requested`` 之前所有非 skipped 节点 completed 且产物文件存在;
           任一缺失 → **回退**到最早的缺失节点起重跑,并记日志说明回退原因。
        2. 清空(回退后)起始节点及其下游的产物与状态 + 任务级 temp 工作区
           (干净工作上下文,**不复用失败节点的半成品**)。
        3. 任务状态 failed / cancelled / completed → running(合法 rerun 迁移)。

        返回实际起始节点(可能因回退早于 requested)。
        """
        start = requested
        # 1. 上游校验 + 回退(按拓扑序找最早的「未 completed 或产物缺失」节点)
        for n in nodes_before(requested):
            ns = self.state.nodes[n]
            if ns.status == NodeStatus.SKIPPED:
                continue
            if ns.status != NodeStatus.COMPLETED:
                start = n
                logger.warning(
                    "重跑回退:上游节点 %s 未 completed,改为从该节点起重跑 task=%s",
                    n.value,
                    self.task_id,
                )
                break
            kind = _PRODUCER_BY_NODE.get(n)
            rel = self.state.artifact(kind) if kind else None
            if rel and self.data_root is not None and not (self.data_root / rel).exists():
                start = n
                logger.warning(
                    "重跑回退:上游节点 %s 产物文件缺失,改为从该节点起重跑 task=%s",
                    n.value,
                    self.task_id,
                )
                break
        # 2. 干净工作上下文:重置 start 及其下游(含 cleanup);复用上游 completed 产物
        for n in nodes_from(start):
            self.state.reset_node(n)
        self._clean_temp()
        # 3. 合法迁移回 running + 清总体 error
        self.state.error = None
        self._transition_task(TaskStatus.RUNNING)
        return start

    def _clean_temp(self) -> None:
        """清空任务级临时工作区 ``data/temp/<task_id>/``(契约 §0.7 / §5.3)。"""
        if self.data_root is None:
            return
        tmp = self.data_root / "temp" / self.task_id
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# 功能糖:run_task_dag
# --------------------------------------------------------------------------- #
def run_task_dag(
    task: Any,
    *,
    download: Optional[NodeExecutor] = None,
    extract_audio: Optional[NodeExecutor] = None,
    asr: Optional[NodeExecutor] = None,
    note: Optional[NodeExecutor] = None,
    mindmap: Optional[NodeExecutor] = None,
    cleanup: Optional[NodeExecutor] = None,
    state: Optional[TaskState] = None,
    repo: Any = None,
    bus: Any = None,
    settings: Any = None,
    data_root: "str | Path | None" = None,
    cancel: Optional[CancelToken] = None,
    from_node: "NodeName | str | None" = None,
    clock: Callable[[], datetime] = datetime.now,
) -> TaskState:
    """六步 DAG 编排函数(设计 D8 / 规格 task-pipeline / 契约 §5 §6.6)。

    接受各步骤的可调用执行器(下载 / 提取音频 / ASR / 笔记 / 思维导图 / 清理),
    推进节点状态、产出产物路径回写 task。本阶段先把框架与状态机做扎实,各执行器
    调用点为清晰钩子,整合阶段接入 ``media_ingest`` / ``speech_to_text`` /
    ``note_generation`` / ``mindmap`` / ``retention`` 等真实模块。

    Args:
        task: 任务对象(需有 ``id`` 与 ``source_type`` 属性;若已含 ``node_statuses``
            则据此加载既有状态,否则按来源构造 fresh 状态)。
        download / extract_audio / asr / note / mindmap / cleanup: 各节点执行器钩子
            ``Callable[[NodeContext], None]``。执行器内通过 ``ctx.register_product``
            登记产物、``ctx.emit_progress`` / ``ctx.emit_log`` 推进度日志、
            ``ctx.cancel.is_cancelled()`` 检查取消;抛 ``PipelineCancelled`` 触发取消、
            抛其它异常触发节点失败。传 ``None`` 的节点按 no-op 完成(整合阶段未接入时)。
        state: 外部传入的既有 :class:`TaskState`(重跑 / 恢复);``None`` 则从 task 加载
            或按来源构造 fresh。
        repo / bus / settings / data_root / cancel / clock: 内核依赖与基础设施(可选,
            默认内存 / no-op,便于无基础设施时单测)。
        from_node: 节点级重跑起始节点;``None`` 为完整执行。

    Returns:
        最终 :class:`TaskState`;同时把 ``status`` / ``progress`` / ``node_statuses`` /
        各产物路径回写到 task 对象(可写属性时)。
    """
    task_id = str(_get(task, "id"))
    source_type = _get(task, "source_type")
    if state is None:
        state = _load_state_from_task(task) or TaskState.fresh(task_id, source_type)
    # fresh 任务(尚无 node_statuses)若已由上传登记顶层产物指针(如 local_audio 的
    # audio_path / local_video 的 video_path),同步进 state.artifacts,供下游节点
    # 「缺上游产物」校验通过(契约 §1.2:skipped 节点 product 仍为 null,仅顶层指针有值)。
    _sync_artifacts_from_task(task, state)

    executors: dict[NodeName, NodeExecutor] = {}
    for node, ex in (
        (NodeName.DOWNLOAD, download),
        (NodeName.EXTRACT_AUDIO, extract_audio),
        (NodeName.ASR, asr),
        (NodeName.NOTE, note),
        (NodeName.MINDMAP, mindmap),
        (NodeName.CLEANUP, cleanup),
    ):
        if ex is not None:
            executors[node] = ex

    runner = DagRunner(
        task_id,
        state=state,
        repo=repo,
        bus=bus,
        settings=settings,
        data_root=data_root,
        executors=executors,
        cancel=cancel,
        clock=clock,
        task=task,
    )
    final = runner.run(from_node=from_node)
    _write_back_to_task(task, final)
    return final


# --------------------------------------------------------------------------- #
# 重启恢复(规格 task-pipeline / 契约 §0.9)
# --------------------------------------------------------------------------- #
def recover_running_on_startup(
    state: TaskState, *, clock: Callable[[], datetime] = datetime.now
) -> bool:
    """后端重启恢复:把残留 ``running`` 的任务标 ``failed``(规格 task-pipeline / 契约 §0.9)。

    error 注明「重启中断于 <节点名> 节点」,MUST NOT 让其永久卡在 running。
    running 节点(若有)置节点级 failed。调用方负责随后 ``repo.update_task_state`` 落库。

    Returns:
        是否发生了恢复(即原状态确为 running)。
    """
    if state.status != TaskStatus.RUNNING:
        return False
    node = state.running_node()
    node_label = node.value if node is not None else "未知"
    err = f"重启中断于 {node_label} 节点"
    if node is not None:
        ns = state.nodes[node]
        ns.status = NodeStatus.FAILED
        ns.error = err
        ns.finished_at = clock().isoformat()
    # running → failed 为合法迁移,用状态机函数迁(同时校验合法性)
    state.status = transition_task_status(state.status, TaskStatus.FAILED)
    state.error = err
    state.finished_at = clock().isoformat()
    return True


# --------------------------------------------------------------------------- #
# Task 读写小工具(鸭子类型,容忍旧/新 Task 形态)
# --------------------------------------------------------------------------- #
def _get(obj: Any, attr: str, default: Any = None) -> Any:
    """从对象(属性)或字典(key)取值,统一容忍 dataclass / dict / namespace。"""
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def _try_set(obj: Any, attr: str, value: Any) -> None:
    """尽力写回属性(只读对象 / 旧字段缺失时静默跳过,不阻断编排)。"""
    try:
        if isinstance(obj, dict):
            obj[attr] = value
        else:
            setattr(obj, attr, value)
    except Exception:  # noqa: BLE001 - 回写失败不得阻断编排
        logger.debug("回写任务字段失败 attr=%s", attr, exc_info=True)


def _sync_artifacts_from_task(task: Any, state: TaskState) -> None:
    """把任务顶层产物指针(video_path / audio_path / ...)同步进 state.artifacts。

    用于 fresh 任务:上传文件(local_audio 的 audio_path、local_video 的 video_path)
    在任务创建时即登记到顶层,但此时尚无 node_statuses;不同步则下游节点的「缺上游产物」
    校验会误判。仅登记顶层指针,**不**写 skipped 节点的 product(契约 §1.2)。
    """
    for kind, field_name in ARTIFACT_TASK_FIELD.items():
        v = _get(task, field_name, None)
        if v and not state.artifacts.get(kind):
            state.artifacts[kind] = str(v)


def _load_state_from_task(task: Any) -> Optional[TaskState]:
    """若 task 已含 ``node_statuses`` 字典,据此构造 TaskState;否则返回 None(走 fresh)。"""
    ns = _get(task, "node_statuses", None)
    if not ns:
        return None
    state = TaskState(
        task_id=str(_get(task, "id")),
        source_type=_coerce_source(_get(task, "source_type")).value,
    )
    try:
        state.status = _coerce_task_status(_get(task, "status", TaskStatus.PENDING))
    except ValueError:
        state.status = TaskStatus.PENDING
    state.error = _get(task, "error", None)
    for n in NODE_ORDER:
        state.nodes[n] = NodeState.from_dict(ns.get(n.value) or {})
    for kind, field_name in ARTIFACT_TASK_FIELD.items():
        v = _get(task, field_name, None)
        if v:
            state.artifacts[kind] = str(v)
    mm = _get(task, "mindmap_paths", None)
    if mm:
        state.mindmap_paths = [str(x) for x in mm]
    sc = _get(task, "screenshot_paths", None)
    if sc:
        state.screenshot_paths = [str(x) for x in sc]
    return state


def _write_back_to_task(task: Any, state: TaskState) -> None:
    """把最终状态与产物路径回写到 task 对象(可写字段时;契约 §1.1 / §1.2 同步)。"""
    _try_set(task, "status", state.status.value)
    _try_set(task, "progress", state.progress)
    _try_set(task, "node_statuses", state.to_node_statuses_dict())
    _try_set(task, "error", state.error)
    for kind, field_name in ARTIFACT_TASK_FIELD.items():
        _try_set(task, field_name, state.artifacts.get(kind))
    _try_set(task, "mindmap_paths", list(state.mindmap_paths))
    _try_set(task, "screenshot_paths", list(state.screenshot_paths))
    if state.finished_at:
        _try_set(task, "finished_at", state.finished_at)


__all__ = [
    # 运行时模型
    "NodeState",
    "TaskState",
    # 桥接
    "NodeContext",
    "CancelToken",
    "PipelineCancelled",
    "NodeExecutor",
    # 编排
    "DagRunner",
    "run_task_dag",
    "recover_running_on_startup",
]
