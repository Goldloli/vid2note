"""
pipeline —— 六步 DAG 编排层(设计 D8 / 规格 task-pipeline / 契约 §5 §6.6)
=======================================================================

将每个任务编排为一个固定拓扑序的六节点有向无环图:

    download → extract_audio → asr → note → mindmap → cleanup

每个节点维护独立的状态机(``pending / running / completed / failed / skipped``)
与进度(0–100);任务总体状态机(``pending / running / completed / failed / cancelled``)
仅允许既定迁移。按媒体来源跳过 download / extract_audio;cleanup 在成功与失败两条
路径都执行;节点缺上游产物即终止;支持从指定节点重跑(复用上游 completed 产物、
级联重算下游、干净工作上下文)。

公共 API:

- 状态机与规则(``states``):``NodeName`` / ``NodeStatus`` / ``TaskStatus`` /
  ``NODE_ORDER`` / ``TASK_TRANSITIONS`` / ``skip_nodes_for`` /
  ``transition_task_status`` / ``is_legal_task_transition`` 等。
- 运行时与编排(``dag``):``TaskState`` / ``NodeContext`` / ``DagRunner`` /
  ``run_task_dag`` / ``recover_running_on_startup``。

内核边界:``logger`` 经 ``from src.core.kernel import`` 取;本包其余能力均为新增,
不穿透内核内部(契约 §0.2)。
"""
from .dag import (
    CancelToken,
    DagRunner,
    NodeContext,
    NodeExecutor,
    NodeState,
    PipelineCancelled,
    TaskState,
    recover_running_on_startup,
    run_task_dag,
)
from .states import (
    ARTIFACT_TASK_FIELD,
    NODE_ORDER,
    NODE_WEIGHTS,
    REQUIRED_ARTIFACT,
    TASK_TRANSITIONS,
    TERMINAL_TASK_STATUSES,
    IllegalTransitionError,
    NodeName,
    NodeStatus,
    SourceType,
    TaskStatus,
    first_executable_node,
    is_legal_task_transition,
    node_index,
    nodes_before,
    nodes_from,
    skip_nodes_for,
    transition_task_status,
)

__all__ = [
    # 枚举与常量
    "NodeName",
    "NodeStatus",
    "TaskStatus",
    "SourceType",
    "NODE_ORDER",
    "NODE_WEIGHTS",
    "REQUIRED_ARTIFACT",
    "ARTIFACT_TASK_FIELD",
    "TASK_TRANSITIONS",
    "TERMINAL_TASK_STATUSES",
    # 异常与规则
    "IllegalTransitionError",
    "is_legal_task_transition",
    "transition_task_status",
    "skip_nodes_for",
    # 拓扑辅助
    "node_index",
    "nodes_before",
    "nodes_from",
    "first_executable_node",
    # 运行时模型
    "NodeState",
    "TaskState",
    "NodeContext",
    "CancelToken",
    "PipelineCancelled",
    "NodeExecutor",
    # 编排
    "DagRunner",
    "run_task_dag",
    "recover_running_on_startup",
]
