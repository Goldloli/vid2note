"""
runtime —— v1 任务运行栈(契约 §5 / 设计 D8)
============================================

整合层:把已就绪的 ``media_ingest`` / ``speech_to_text`` / ``screenshot`` /
``pipeline.dag`` / ``retention`` / ``sse`` 与内核 ``SimpleProcessor`` / ``LLMFactory``
接入六步 DAG,对外提供任务运行栈的三个支柱:

- :mod:`runtime.runner` —— :func:`run_task` 执行单个任务(DAG 编排)。
- :mod:`runtime.task_service` —— :class:`TaskService` 任务编排服务(创建/查询/重跑/
  取消/历史/批量)。
- :mod:`runtime.worker` —— :class:`RuntimeWorker` asyncio 队列消费者(受限并发执行)。

辅助:
- :mod:`runtime.settings` —— 设置快照与合法默认值(契约 §3.2)。
- :mod:`runtime.adapters` —— DAG 与 TaskRepository / SSEBus 之间的适配层。

内核边界(契约 §0.2):``SimpleProcessor`` / ``LLMFactory`` / ``TaskRepository`` /
``logger`` / ``TaskLogger`` 经 ``from src.core.kernel import`` 取,不穿透内核内部。
"""
from .adapters import (
    CancelRegistry,
    RepoStateAdapter,
    SSEBusAdapter,
    get_cancel_registry,
)
from .runner import run_task
from .settings import (
    DEFAULT_CONCURRENCY,
    DEFAULT_SETTINGS,
    MAX_CONCURRENCY,
    MIN_CONCURRENCY,
    clamp_concurrency,
    get_credentials,
    get_settings_snapshot,
)
from .task_service import TaskService, get_task_service
from .worker import (
    RuntimeWorker,
    enqueue,
    get_worker,
    mark_skip,
    start_worker,
    stop_worker,
)

__all__ = [
    # runner
    "run_task",
    # task_service
    "TaskService",
    "get_task_service",
    # worker
    "RuntimeWorker",
    "enqueue",
    "mark_skip",
    "get_worker",
    "start_worker",
    "stop_worker",
    # settings
    "DEFAULT_SETTINGS",
    "DEFAULT_CONCURRENCY",
    "MIN_CONCURRENCY",
    "MAX_CONCURRENCY",
    "clamp_concurrency",
    "get_settings_snapshot",
    "get_credentials",
    # adapters
    "RepoStateAdapter",
    "SSEBusAdapter",
    "CancelRegistry",
    "get_cancel_registry",
]
