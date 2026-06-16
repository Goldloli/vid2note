"""
Task worker: polls pending tasks and executes PipelineDAG.
"""

import asyncio
import contextlib
import logging
from datetime import datetime

from vid2note_core.events.bus import TaskEvent, get_event_bus
from vid2note_core.pipeline.context import TaskContext
from vid2note_core.pipeline.dag import PipelineDAG
from vid2note_core.pipeline.node import PipelineNode
from vid2note_core.pipeline.real_nodes import (
    RealCleanupNode,
    RealDownloadNode,
    RealExtractAudioNode,
    RealMindmapNode,
    RealOrganizeNode,
    RealTranscribeNode,
)
from vid2note_core.storage.task_repo import TaskRepository
from vid2note_core.types import NodeStatus, TaskId, TaskStatus

logger = logging.getLogger(__name__)


class TaskWorker:
    """Background worker that polls pending tasks and runs the pipeline."""

    def __init__(
        self,
        poll_interval: float = 2.0,
        max_concurrent: int = 3,
        nodes: list[PipelineNode] | None = None,
    ):
        self.poll_interval = poll_interval
        self.max_concurrent = max_concurrent
        self._nodes = nodes  # 可注入（测试用）；None 则用默认真实节点链路
        self._running = False
        self._task: asyncio.Task | None = None
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def start(self) -> None:
        """Start the worker loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("TaskWorker started")

    async def stop(self) -> None:
        """Stop the worker loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("TaskWorker stopped")

    async def _loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.exception("Worker tick failed: %s", e)
            await asyncio.sleep(self.poll_interval)

    async def _tick(self) -> None:
        """Reserve and process one pending task."""
        repo = TaskRepository()
        task = repo.reserve_pending_task()
        if task is None:
            return

        async with self._semaphore:
            await self._process(task)

    async def _process(self, task) -> None:
        """Execute the full pipeline for a task."""
        task_id = task.id
        repo = TaskRepository()
        bus = get_event_bus()

        logger.info("[Worker] Processing task %s", task_id)
        repo.update(task_id, status=TaskStatus.RUNNING, current_step="pipeline.started")
        bus.publish(
            TaskEvent(
                task_id=task_id,
                event_type="task.started",
                progress=0,
                message="任务开始处理",
                timestamp=datetime.now().isoformat(),
            )
        )

        try:
            # 优先用 url，其次用本地 video_file 路径
            source = task.video_url or task.video_file
            ctx = TaskContext(
                task_id=TaskId(task_id),
                config={
                    "url": source,
                    "video_url": task.video_url,
                    "llm_provider": task.llm_provider or "mock",
                    "asr_provider": task.asr_provider or "asrtools-b",
                },
            )
            dag = self._build_dag()
            results = await dag.run(ctx)

            # Check if any node failed
            failed = [r for r in results if r.status == NodeStatus.FAILED]
            if failed:
                first = failed[0]
                err_msg = first.error["message"] if first.error else "unknown"
                raise RuntimeError(f"节点 {first.node.value} 失败: {err_msg}")

            repo.update(
                task_id,
                status=TaskStatus.COMPLETED,
                progress=100,
                current_step="pipeline.completed",
            )
            bus.publish(
                TaskEvent(
                    task_id=task_id,
                    event_type="task.completed",
                    progress=100,
                    message="任务完成",
                    timestamp=datetime.now().isoformat(),
                )
            )
            logger.info("[Worker] Task %s completed", task_id)

        except Exception as e:
            logger.exception("[Worker] Task %s failed: %s", task_id, e)
            repo.update(task_id, status=TaskStatus.FAILED, error_message=str(e))
            bus.publish(
                TaskEvent(
                    task_id=task_id,
                    event_type="task.failed",
                    progress=0,
                    message=f"任务失败: {e}",
                    timestamp=datetime.now().isoformat(),
                )
            )

    def _build_dag(self) -> PipelineDAG:
        """Build the default pipeline DAG.

        默认全部使用真实节点（download/extract_audio/transcribe/organize/mindmap/cleanup）。
        测试可通过构造参数注入自定义节点。
        """
        if self._nodes is not None:
            return PipelineDAG(self._nodes)
        return PipelineDAG(
            [
                RealDownloadNode(),
                RealExtractAudioNode(),
                RealTranscribeNode(),
                RealOrganizeNode(),
                RealMindmapNode(),
                RealCleanupNode(),
            ]
        )


# Global singleton
_worker: TaskWorker | None = None


def get_worker() -> TaskWorker:
    global _worker
    if _worker is None:
        _worker = TaskWorker()
    return _worker
