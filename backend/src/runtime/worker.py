"""
runtime.worker —— 简单 asyncio 队列消费者(契约 §0.8 / §3.4 / 设计 D8)
======================================================================

单进程内从 :class:`asyncio.Queue` 取 ``(task_id, from_node)``,在线程池里调
:func:`runtime.runner.run_task` 执行(节点内的 LLM / ffmpeg / yt-dlp 均为同步阻塞调用,
经 :func:`asyncio.to_thread` 放到线程,避免独占事件循环)。

并发上限 ``max_concurrent`` 从设置 ``concurrency.max`` 读(默认 1,范围 1~3,越界回落),
用 :class:`asyncio.Semaphore` 约束同时运行的任务数(契约 §0.8 跨任务共享 CPU/IO 预算)。

异常处理:run_task 内部已把节点异常转为任务 failed 终态(经 DAG);worker 仍兜底捕获
run_task 自身抛出的非节点异常(如任务不存在、状态机非法),标 failed 并推 SSE。

公共 API:``enqueue`` / ``start_worker`` / ``stop_worker`` / ``get_worker`` /
``mark_skip``(供 task_service.cancel 让队列跳过已取消的待运行项)。
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional, Tuple

from src.core.kernel import logger
from src.models.task import TaskStatus

from .adapters import SSEBusAdapter, get_cancel_registry
from .runner import run_task
from .settings import clamp_concurrency, get_settings_snapshot


class RuntimeWorker:
    """asyncio 队列消费者:串行取队、受限并发地执行任务。"""

    def __init__(
        self,
        *,
        repo: Any = None,
        bus: Any = None,
        max_concurrent: Optional[int] = None,
        poll_interval: float = 0.2,
    ) -> None:
        self._repo = repo
        self._bus = bus  # 可选:同步 publish 桩;None 时 runner 内按 loop 桥接 SSEBus
        self._poll_interval = poll_interval
        # 并发上限:显式传入 > 设置快照;None 时延后到 start() 读快照
        self._max_concurrent = max_concurrent
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._queue: asyncio.Queue[Tuple[str, Optional[str]]] = asyncio.Queue()
        self._skip_run: set[str] = set()  # 已取消的待运行 task_id
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._active: set[asyncio.Task] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ---------------- 生命周期 ---------------- #
    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent or 1

    def _resolve_repo(self):
        if self._repo is None:
            from src.core.kernel import TaskRepository

            self._repo = TaskRepository()
        return self._repo

    def _resolve_concurrency(self) -> int:
        """并发上限:显式传入优先;否则从 settings 快照读并 clamp(契约 §0.8)。"""
        if self._max_concurrent is not None:
            return clamp_concurrency(self._max_concurrent)
        try:
            snapshot = get_settings_snapshot(self._resolve_repo())
            return clamp_concurrency(snapshot.get("concurrency.max", 1))
        except Exception:  # noqa: BLE001 - 读设置失败回落默认 1
            logger.debug("读取并发设置失败,回落默认 1", exc_info=True)
            return 1

    async def start(self) -> None:
        """启动消费者循环(幂等;重复调用无副作用)。"""
        if self._running:
            return
        self._loop = asyncio.get_running_loop()
        self._max_concurrent = self._resolve_concurrency()
        self._semaphore = asyncio.Semaphore(self._max_concurrent)
        self._running = True
        self._task = asyncio.create_task(self._loop_main())
        logger.info("[RuntimeWorker] 已启动,最大并发 %d", self._max_concurrent)

    async def stop(self) -> None:
        """停止消费者循环;等待在途任务结束(不强制中断)。"""
        if not self._running:
            return
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        # 等待活跃任务收尾
        if self._active:
            await asyncio.gather(*self._active, return_exceptions=True)
        logger.info("[RuntimeWorker] 已停止")

    # ---------------- 入队 / 取消 ---------------- #
    def enqueue(self, task_id: str, from_node: Optional[str] = None) -> None:
        """把任务投递到运行队列(worker 未启动时也入队,start 后消费)。"""
        self._skip_run.discard(task_id)
        try:
            self._queue.put_nowait((task_id, from_node))
        except asyncio.QueueShuttingDown:  # pragma: no cover - 兼容 3.13
            logger.warning("[RuntimeWorker] 队列已关闭,入队失败 task=%s", task_id)

    def mark_skip(self, task_id: str) -> None:
        """标记某待运行任务为跳过(供 cancel 在 pending 阶段取消用)。"""
        self._skip_run.add(task_id)

    # ---------------- 主循环 ---------------- #
    async def _loop_main(self) -> None:
        """主循环:有并发额度时取队 → to_thread 执行;无额度时短休。"""
        assert self._semaphore is not None
        while self._running:
            # 等待并发额度
            await self._semaphore.acquire()
            try:
                item = await self._drain_next()
            except asyncio.CancelledError:
                self._semaphore.release()
                raise
            if item is None:
                # 被跳过或队列暂时为空:释放额度并短休
                self._semaphore.release()
                await asyncio.sleep(self._poll_interval)
                continue
            task_id, from_node = item
            ao = asyncio.create_task(self._run_one(task_id, from_node))
            self._active.add(ao)
            ao.add_done_callback(self._active.discard)

    async def _drain_next(self) -> Optional[Tuple[str, Optional[str]]]:
        """取下一条非跳过的任务;队空或全被跳过时返回 None。"""
        try:
            task_id, from_node = self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None
        if task_id in self._skip_run:
            self._skip_run.discard(task_id)
            logger.info("[RuntimeWorker] 跳过已取消的待运行任务 task=%s", task_id)
            # 继续看队列里有没有下一条(不阻塞)
            try:
                return self._drain_next_sync()
            except asyncio.QueueEmpty:
                return None
        return (task_id, from_node)

    def _drain_next_sync(self) -> Optional[Tuple[str, Optional[str]]]:
        """同步连续取队直到命中非跳过项或队列空(递归式)。"""
        try:
            task_id, from_node = self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None
        if task_id in self._skip_run:
            self._skip_run.discard(task_id)
            return self._drain_next_sync()
        return (task_id, from_node)

    async def _run_one(self, task_id: str, from_node: Optional[str]) -> None:
        """执行单个任务(在线程池跑同步 DAG),兜底捕获异常。"""
        repo = self._resolve_repo()
        loop = self._loop or asyncio.get_running_loop()
        bus = self._bus  # None 时 runner 内按 loop 桥接 SSEBus
        try:
            await asyncio.to_thread(
                run_task,
                task_id,
                from_node=from_node,
                repo=repo,
                bus=bus,
                loop=loop,
            )
        except Exception as exc:  # noqa: BLE001 - run_task 自身异常(非节点级)兜底
            logger.error("[RuntimeWorker] 任务执行异常 task=%s: %s", task_id, exc, exc_info=True)
            await self._mark_failed(repo, loop, task_id, str(exc))
        finally:
            self._semaphore.release() if self._semaphore else None

    async def _mark_failed(self, repo: Any, loop: Any, task_id: str, error: str) -> None:
        """兜底标 failed + 推 SSE(仅在 run_task 未能自行转终态时生效)。"""
        try:
            task = await asyncio.to_thread(repo.get_by_id, task_id)
            if task is None:
                return
            cur = task.status.value if hasattr(task.status, "value") else str(task.status)
            if cur in (TaskStatus.RUNNING.value, TaskStatus.PENDING.value):
                await asyncio.to_thread(repo.fail_task, task_id, f"运行栈异常:{error}")
                await self._publish_terminal(loop, task_id, "task-failed", {"error": error})
        except Exception:  # noqa: BLE001 - 兜底失败不得拖垮主循环
            logger.debug("[RuntimeWorker] 兜底标 failed 失败 task=%s", task_id, exc_info=True)

    async def _publish_terminal(self, loop: Any, task_id: str, event: str, payload: dict) -> None:
        """推一个终态 SSE 事件(尽力而为)。"""
        try:
            from src.sse import get_bus

            bus = get_bus()
            if loop is not None and loop.is_running():
                await bus.publish(task_id, event, payload)
        except Exception:  # noqa: BLE001
            logger.debug("[RuntimeWorker] 终态事件推送失败 task=%s", task_id, exc_info=True)


# --------------------------------------------------------------------------- #
# 进程内单例
# --------------------------------------------------------------------------- #
_worker: Optional[RuntimeWorker] = None


def get_worker(*, repo: Any = None, max_concurrent: Optional[int] = None) -> RuntimeWorker:
    """获取全局 RuntimeWorker 单例(首次取时构造,复用既有实例)。"""
    global _worker
    if _worker is None:
        _worker = RuntimeWorker(repo=repo, max_concurrent=max_concurrent)
    return _worker


def enqueue(task_id: str, from_node: Optional[str] = None) -> None:
    """投递任务到全局 worker 队列。"""
    get_worker().enqueue(task_id, from_node)


def mark_skip(task_id: str) -> None:
    """标记全局 worker 队列中某任务为跳过(取消 pending 任务用)。"""
    get_worker().mark_skip(task_id)


async def start_worker(*, repo: Any = None, max_concurrent: Optional[int] = None) -> RuntimeWorker:
    """启动全局 worker(幂等;若已存在实例则复用其并发配置)。"""
    global _worker
    if _worker is None:
        _worker = RuntimeWorker(repo=repo, max_concurrent=max_concurrent)
    await _worker.start()
    return _worker


async def stop_worker() -> None:
    """停止全局 worker(清空单例,下次 start 重建以应用新并发配置)。"""
    global _worker
    if _worker is not None:
        await _worker.stop()
        _worker = None


__all__ = [
    "RuntimeWorker",
    "get_worker",
    "enqueue",
    "mark_skip",
    "start_worker",
    "stop_worker",
]
