"""
六步 DAG 节点与任务状态定义(规格 task-pipeline / 设计 D8)
============================================================

本模块定义六节点流水线 DAG 的**拓扑**、**单节点状态机**、**任务总体状态机**及其
合法迁移,以及按媒体来源(`source_type`)驱动的节点跳过规则。

本文件为**纯数据与规则**,无任何 I/O 依赖(不碰 SQLite / 文件 / 网络),
便于对状态机做确定性单测(见 `tests/test_dag.py`)。

契约对照:
- `backend/CONTRACT.md` §1.3(总体状态合法迁移)
- `backend/CONTRACT.md` §5.1 / §5.5(DAG 拓扑与来源跳过)
- `backend/CONTRACT.md` §6.6(`NodeName` / `NODE_ORDER` / `skip_nodes_for`)
"""
from __future__ import annotations

from enum import Enum
from typing import Iterable


# --------------------------------------------------------------------------- #
# 枚举
# --------------------------------------------------------------------------- #
class NodeName(str, Enum):
    """六节点名称(DAG 拓扑序,**顺序 MUST NOT 改变**)。

    顺序即执行顺序:下载 → 提取音频 → ASR → 笔记 → 思维导图 → 清理。
    枚举值同时是 `node_statuses` 的 JSON key 与 SSE 事件的 `node` 字段,
    故取值不得变更。
    """

    DOWNLOAD = "download"
    EXTRACT_AUDIO = "extract_audio"
    ASR = "asr"
    NOTE = "note"
    MINDMAP = "mindmap"
    CLEANUP = "cleanup"


class NodeStatus(str, Enum):
    """单个节点的运行状态(规格 task-pipeline)。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskStatus(str, Enum):
    """任务总体状态(仅允许 :data:`TASK_TRANSITIONS` 内的迁移)。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SourceType(str, Enum):
    """媒体来源类型(值与 ``media_ingest.SourceType`` 对齐)。

    设计 D6 / 契约 §6.1:``youtube`` / ``bilibili`` / ``direct`` 为在线视频平台,
    ``local_video`` / ``local_audio`` 为本地上传。来源类型驱动 download / extract_audio
    节点的跳过(契约 §5.5)。

    本包内**自洽定义**、不依赖尚未实现的 ``media_ingest`` 包;两者均为 ``str`` 枚举、
    取值一致,可按字符串值互换比较。
    """

    YOUTUBE = "youtube"
    BILIBILI = "bilibili"
    DIRECT = "direct"
    LOCAL_VIDEO = "local_video"
    LOCAL_AUDIO = "local_audio"


# --------------------------------------------------------------------------- #
# DAG 拓扑
# --------------------------------------------------------------------------- #
NODE_ORDER: list[NodeName] = [
    NodeName.DOWNLOAD,
    NodeName.EXTRACT_AUDIO,
    NodeName.ASR,
    NodeName.NOTE,
    NodeName.MINDMAP,
    NodeName.CLEANUP,
]
"""六节点 DAG 拓扑序(固定,顺序即执行顺序)。"""


TERMINAL_TASK_STATUSES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
)
"""任务终态集合:进入后除「节点级 rerun 回 running」外不可再迁移。"""


# 合法的任务总体状态迁移表(契约 §1.3 / 规格 task-pipeline)。
#
#   pending    → running / cancelled
#   running    → completed / failed / cancelled
#   failed     → running        # 仅经节点级 rerun 触发(合法)
#   cancelled  → running        # 仅经节点级 rerun 触发(合法)
#   completed  → running        # 仅经节点级 rerun 触发(合法,见 spec「用户可手动选择从更早节点重跑」)
#
# 注:契约 §1.3 文字示例把 ``completed→running`` 列为「未经 rerun」时的非法迁移,
# 其语义是「回到 running 的唯一合法途径是节点级 rerun」;这与规格 task-pipeline
# 「已 completed 任务可从更早节点重跑」场景一致 —— 故把 completed→running 视为合法 rerun 通道。
TASK_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.RUNNING, TaskStatus.CANCELLED}),
    TaskStatus.RUNNING: frozenset(
        {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.COMPLETED: frozenset({TaskStatus.RUNNING}),
    TaskStatus.FAILED: frozenset({TaskStatus.RUNNING}),
    TaskStatus.CANCELLED: frozenset({TaskStatus.RUNNING}),
}
"""任务总体状态的合法迁移邻接表(值为可迁入的目标状态集合)。"""


# 节点权重(用于总体进度加权聚合;契约 §5.4:cleanup 权重较小,skipped 节点按 100 计)。
# 权重反映各步典型耗时占比,五权重大头分配给下载/ASR/笔记,cleanup 仅占 5。
NODE_WEIGHTS: dict[NodeName, int] = {
    NodeName.DOWNLOAD: 25,
    NodeName.EXTRACT_AUDIO: 5,
    NodeName.ASR: 30,
    NodeName.NOTE: 25,
    NodeName.MINDMAP: 10,
    NodeName.CLEANUP: 5,
}


# 各非 cleanup 节点开始前**必需的上游产物类别**(契约 §5.1 数据流 / §5.2.2 缺产物终止)。
# download 与 cleanup 无产物依赖(分别依赖 source_url 与全部产物列表)。
# 产物路径取自顶层便捷指针(video_path / audio_path / srt_path / note_path),
# 它们由产出节点 product 或本地上传直接登记(契约 §1.2),二者保持同步。
REQUIRED_ARTIFACT: dict[NodeName, str | None] = {
    NodeName.DOWNLOAD: None,
    NodeName.EXTRACT_AUDIO: "video",
    NodeName.ASR: "audio",
    NodeName.NOTE: "srt",
    NodeName.MINDMAP: "note",
    NodeName.CLEANUP: None,
}


# 产物类别 → 任务顶层便捷指针字段名(契约 §1.1 / §1.2)。
# DAG 完成节点时据此把产物路径同步写到任务顶层字段,便于历史视图与下载接口直接消费。
ARTIFACT_TASK_FIELD: dict[str, str] = {
    "video": "video_path",
    "audio": "audio_path",
    "srt": "srt_path",
    "note": "note_path",
}


# --------------------------------------------------------------------------- #
# 异常
# --------------------------------------------------------------------------- #
class IllegalTransitionError(ValueError):
    """非法的任务总体状态迁移。

    由 :func:`transition_task_status` 在遇到非既定迁移时抛出;调用方(Worker / API /
    DagRunner)MUST 捕获、**保持原状态不变**,并记一次非法迁移尝试日志
    (规格 task-pipeline「仅允许既定的状态迁移」)。
    """


# --------------------------------------------------------------------------- #
# 状态机迁移规则
# --------------------------------------------------------------------------- #
def _coerce_task_status(value: "TaskStatus | str") -> TaskStatus:
    if isinstance(value, TaskStatus):
        return value
    return TaskStatus(str(value))


def _coerce_node(value: "NodeName | str") -> NodeName:
    if isinstance(value, NodeName):
        return value
    return NodeName(str(value))


def _coerce_source(value: "SourceType | str | None") -> SourceType:
    if isinstance(value, SourceType):
        return value
    if value is None:
        return SourceType.DIRECT
    return SourceType(str(value))


def is_legal_task_transition(src: "TaskStatus | str", dst: "TaskStatus | str") -> bool:
    """判断 ``src → dst`` 是否为既定的合法任务状态迁移。"""
    s = _coerce_task_status(src)
    d = _coerce_task_status(dst)
    return d in TASK_TRANSITIONS.get(s, frozenset())


def transition_task_status(src: "TaskStatus | str", dst: "TaskStatus | str") -> TaskStatus:
    """执行任务状态迁移;非法则抛 :class:`IllegalTransitionError`。

    调用方负责捕获并记日志、保持原状态不变(规格 task-pipeline)。
    """
    s = _coerce_task_status(src)
    d = _coerce_task_status(dst)
    if not is_legal_task_transition(s, d):
        raise IllegalTransitionError(
            f"非法的任务状态迁移:{s.value} → {d.value}(仅允许既定迁移)"
        )
    return d


# --------------------------------------------------------------------------- #
# 来源驱动的节点跳过(契约 §5.5)
# --------------------------------------------------------------------------- #
# 各来源类型对应的「跳过节点集合」。
# - local_video:跳过 download(上传视频文件直接登记为 video_path)
# - local_audio:跳过 download 与 extract_audio(上传音频文件直接登记为 audio_path)
# - 在线来源(youtube / bilibili / direct):不跳过任何节点
_SOURCE_SKIP_MAP: dict[SourceType, frozenset[NodeName]] = {
    SourceType.YOUTUBE: frozenset(),
    SourceType.BILIBILI: frozenset(),
    SourceType.DIRECT: frozenset(),
    SourceType.LOCAL_VIDEO: frozenset({NodeName.DOWNLOAD}),
    SourceType.LOCAL_AUDIO: frozenset({NodeName.DOWNLOAD, NodeName.EXTRACT_AUDIO}),
}


def skip_nodes_for(source_type: "SourceType | str") -> set[NodeName]:
    """按媒体来源返回应被跳过(skipped)的节点集合(契约 §5.5 / §6.6)。

    - ``local_video`` → ``{download}``(上传视频文件直接登记为 video_path)
    - ``local_audio`` → ``{download, extract_audio}``(上传音频文件直接登记为 audio_path)
    - 在线来源(``youtube`` / ``bilibili`` / ``direct``)→ 空集
    """
    st = _coerce_source(source_type)
    return set(_SOURCE_SKIP_MAP.get(st, frozenset()))


# --------------------------------------------------------------------------- #
# 拓扑序辅助
# --------------------------------------------------------------------------- #
def node_index(node: "NodeName | str") -> int:
    """返回节点在 :data:`NODE_ORDER` 中的下标(0 起)。"""
    return NODE_ORDER.index(_coerce_node(node))


def nodes_before(node: "NodeName | str") -> list[NodeName]:
    """返回该节点之前的全部上游节点(不含自身),按拓扑序。"""
    return NODE_ORDER[: node_index(node)]


def nodes_from(node: "NodeName | str") -> list[NodeName]:
    """返回该节点及其全部下游(含自身),按拓扑序;用于重跑级联范围。"""
    return NODE_ORDER[node_index(node) :]


def first_executable_node(skip: "Iterable[NodeName] | None" = None) -> NodeName:
    """返回首个非 skipped 的节点(worker 取起任务后进入 running 的首节点)。

    cleanup 永不跳过,故恒有解。
    """
    skip_set = set(skip or ())
    for n in NODE_ORDER:
        if n not in skip_set:
            return n
    return NodeName.CLEANUP


__all__ = [
    # 枚举
    "NodeName",
    "NodeStatus",
    "TaskStatus",
    "SourceType",
    # 拓扑
    "NODE_ORDER",
    "TERMINAL_TASK_STATUSES",
    "TASK_TRANSITIONS",
    "NODE_WEIGHTS",
    "REQUIRED_ARTIFACT",
    "ARTIFACT_TASK_FIELD",
    # 异常
    "IllegalTransitionError",
    # 规则
    "is_legal_task_transition",
    "transition_task_status",
    "skip_nodes_for",
    # 辅助
    "node_index",
    "nodes_before",
    "nodes_from",
    "first_executable_node",
]
