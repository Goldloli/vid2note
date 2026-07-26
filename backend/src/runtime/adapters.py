"""
runtime.adapters —— DAG 框架与 TaskRepository / SSEBus 之间的适配层
==================================================================

DAG 框架(``pipeline.dag``)通过两个鸭子类型钩子与外部基础设施解耦:

- ``repo.update_task_state(task_id, state: TaskState) -> None``:把 :class:`TaskState`
  落库(由 :class:`RepoStateAdapter` 适配 v1 ``TaskRepository.update``)。
- ``bus.publish(task_id, event_type, data) -> None``:推 SSE 事件(由
  :class:`SSEBusAdapter` 把**同步调用**桥接到**异步** :class:`sse.SSEBus.publish`)。

本层确保「状态先落库再推 SSE」(契约 §0 第 5 条)由 DAG 框架统一保证,适配器只做翻译。

另外提供 :class:`CancelRegistry`:任务级 :class:`CancelToken` 的进程内注册表,
供 runner 登记、task_service.cancel 取消运行中任务(契约 §0.6 取消协议)。
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any, Dict, Optional

from src.core.kernel import logger
from src.pipeline import CancelToken


# --------------------------------------------------------------------------- #
# Repo 适配器:TaskState → TaskRepository.update
# --------------------------------------------------------------------------- #
class RepoStateAdapter:
    """把 DAG 的 :class:`TaskState` 翻译为 ``TaskRepository.update`` 调用。

    DAG 在每次节点/任务状态变化时经 ``repo.update_task_state(task_id, state)``
    调用本适配器(契约 §0 第 5 条「状态先落库」)。本适配器把 state 的字段映射到
    v1 ``Task`` 的列:总体 status/progress/error/node_statuses、顶层产物指针
    (video/audio/srt/note)、多产物列表(mindmap/screenshot)、finished_at。
    """

    def __init__(self, repo: Any) -> None:
        self._repo = repo

    def update_task_state(self, task_id: str, state: Any) -> None:
        """落库 TaskState(对齐 CONTRACT §1.1 字段)。"""
        status = state.status
        status_value = status.value if hasattr(status, "value") else str(status)
        kwargs: Dict[str, Any] = {
            "status": status_value,
            "progress": int(getattr(state, "progress", 0) or 0),
            "node_statuses": state.to_node_statuses_dict(),
            "error": getattr(state, "error", None),
            "video_path": state.artifacts.get("video"),
            "audio_path": state.artifacts.get("audio"),
            "srt_path": state.artifacts.get("srt"),
            "note_path": state.artifacts.get("note"),
            "mindmap_paths": list(getattr(state, "mindmap_paths", []) or []),
            "screenshot_paths": list(getattr(state, "screenshot_paths", []) or []),
        }
        finished_at = getattr(state, "finished_at", None)
        if finished_at:
            kwargs["finished_at"] = finished_at
        self._repo.update(task_id, **kwargs)


# --------------------------------------------------------------------------- #
# SSE 总线适配器:同步 publish → 异步 SSEBus.publish
# --------------------------------------------------------------------------- #
class SSEBusAdapter:
    """把 DAG 的**同步** ``publish`` 调用桥接到**异步** :class:`sse.SSEBus`。

    DAG 在线程内运行(worker 经 ``asyncio.to_thread`` 调 runner);本适配器持有
    worker 的事件循环引用,通过 :func:`asyncio.run_coroutine_threadsafe` 把事件
    投递回事件循环线程。无事件循环(如纯同步调用/单测)时静默丢弃事件,不阻断编排。

    publish 内部仅 ``put_nowait``(订阅者队列),正常近瞬时完成;设短超时以防事件
    循环阻塞时拖累 DAG 线程。任何异常(含超时)都吞掉 —— SSE 是瞬态,不得影响权威态。
    """

    def __init__(self, bus: Any, loop: Optional[asyncio.AbstractEventLoop]) -> None:
        self._bus = bus
        self._loop = loop

    def publish(self, task_id: str, event_type: str, data: dict) -> None:
        if self._bus is None:
            return
        loop = self._loop
        if loop is None or not loop.is_running():
            return  # 无运行中的事件循环:丢弃事件(DAG 仍正常落库)
        try:
            fut = asyncio.run_coroutine_threadsafe(
                self._bus.publish(task_id, event_type, data), loop
            )
            fut.result(timeout=2.0)
        except Exception:  # noqa: BLE001 - SSE 推送失败不得阻断编排
            logger.debug("SSE 事件推送失败/超时 task=%s event=%s", task_id, event_type, exc_info=True)


# --------------------------------------------------------------------------- #
# CancelToken 注册表:runner 登记 / task_service.cancel 取消
# --------------------------------------------------------------------------- #
class CancelRegistry:
    """运行中任务的 :class:`CancelToken` 注册表(线程安全)。

    runner 在任务开始时登记令牌、结束时移除;``cancel(task_id)`` 据此向运行中
    任务发取消信号(契约 §0.6)。
    """

    def __init__(self) -> None:
        self._tokens: Dict[str, CancelToken] = {}
        self._lock = threading.Lock()

    def register(self, task_id: str, token: CancelToken) -> None:
        with self._lock:
            self._tokens[task_id] = token

    def unregister(self, task_id: str) -> None:
        with self._lock:
            self._tokens.pop(task_id, None)

    def get(self, task_id: str) -> Optional[CancelToken]:
        with self._lock:
            return self._tokens.get(task_id)

    def cancel(self, task_id: str) -> bool:
        """向运行中任务发取消信号;返回是否找到了运行中的令牌。"""
        with self._lock:
            token = self._tokens.get(task_id)
        if token is None:
            return False
        token.cancel()
        return True


# 进程内单例
_cancel_registry: Optional[CancelRegistry] = None


def get_cancel_registry() -> CancelRegistry:
    """全局 CancelRegistry 单例。"""
    global _cancel_registry
    if _cancel_registry is None:
        _cancel_registry = CancelRegistry()
    return _cancel_registry


__all__ = [
    "RepoStateAdapter",
    "SSEBusAdapter",
    "CancelRegistry",
    "get_cancel_registry",
]
