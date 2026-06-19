"""
Task worker: polls pending tasks and executes PipelineDAG.
"""

import asyncio
import contextlib
import logging
import os
import signal
from datetime import datetime

from vid2note_core.asr.local.model_manager import ModelManager
from vid2note_core.errors import Vid2NoteError
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
    RealProposeWikiChangesNode,
    RealRegisterSourceNode,
    RealTranscribeNode,
)
from vid2note_core.source.registrar import SourceRegistrar
from vid2note_core.storage.artifact_store import ArtifactStore
from vid2note_core.storage.task_repo import TaskRepository
from vid2note_core.storage.upload_store import UploadStore
from vid2note_core.types import NodeFailure, NodeName, NodeStatus, TaskId, TaskStatus
from vid2note_core.vault.repository import VaultRepository
from vid2note_core.wiki.store import ChangeSetStore

logger = logging.getLogger(__name__)

# provider → (默认 model, 环境变量名) 映射，用于从环境变量解析 API Key
_LLM_PROVIDER_ENV = {
    "qwen": ("qwen-turbo", "DASHSCOPE_API_KEY"),
    "glm": ("glm-4-flash", "ZHIPU_API_KEY"),
    "deepseek": ("deepseek-chat", "DEEPSEEK_API_KEY"),
    "moonshot": ("moonshot-v1-8k", "MOONSHOT_API_KEY"),
    "baidu": ("ernie-bot-4", "BAIDU_API_KEY"),
    "doubao": ("doubao-pro-4k", "VOLCANO_API_KEY"),
}


def _resolve_llm_creds(provider: str) -> tuple[str, str]:
    """根据 provider 从环境变量解析 (api_key, model)。

    qwen 用 DASHSCOPE_API_KEY（阿里云百炼）。
    """
    default_model, env_name = _LLM_PROVIDER_ENV.get(
        provider, ("mock", f"{provider.upper()}_API_KEY")
    )
    api_key = os.environ.get(env_name, "mock_key" if provider == "mock" else "")
    model = os.environ.get(f"{provider.upper()}_MODEL", default_model)
    return api_key, model


def _resolve_llm_config(provider: str) -> dict[str, str]:
    api_key, model = _resolve_llm_creds(provider)
    config = {"api_key": api_key, "llm_model": model}
    if provider == "baidu":
        config["secret_key"] = os.environ.get("BAIDU_SECRET_KEY", "")
    return config


class TaskWorker:
    """Background worker that polls pending tasks and runs the pipeline."""

    def __init__(
        self,
        repository: TaskRepository,
        artifacts: ArtifactStore,
        poll_interval: float = 2.0,
        max_concurrent: int = 3,
        max_retries: int = 3,
        shutdown_timeout: float = 30.0,
        nodes: list[PipelineNode] | None = None,
        uploads: UploadStore | None = None,
        models: ModelManager | None = None,
        source_registrar: SourceRegistrar | None = None,
        vault: VaultRepository | None = None,
        changesets: ChangeSetStore | None = None,
    ):
        self.poll_interval = poll_interval
        self.max_concurrent = max_concurrent
        self.max_retries = max_retries
        self.shutdown_timeout = shutdown_timeout
        self.repository = repository
        self.artifacts = artifacts
        self.uploads = uploads
        self.models = models
        self.source_registrar = source_registrar
        self.vault = vault
        self.changesets = changesets
        self._nodes = nodes  # 可注入（测试用）；None 则用默认真实节点链路
        self._running = False
        self._task: asyncio.Task | None = None
        self._active: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        """Start the worker loop."""
        if self._running:
            return
        self._running = True
        # 启动时恢复上次崩溃留下的 RUNNING 任务（进程被 kill 后未正常关闭）
        await self._recover_stale_tasks()
        # 注册信号处理：SIGTERM/SIGINT 时优雅关闭
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
        self._task = asyncio.create_task(self._loop())
        logger.info("TaskWorker started")

    async def _recover_stale_tasks(self) -> None:
        """启动时把进程崩溃遗留的 RUNNING 任务标记为已中断。"""
        repo = self.repository
        try:
            stale = repo.list_all(status=TaskStatus.RUNNING, limit=100)
            for task in stale:
                logger.warning("恢复残留 RUNNING 任务: %s", task.id)
                repo.update(task.id, status=TaskStatus.INTERRUPTED)
        except Exception as e:
            logger.warning("恢复残留任务失败（可忽略）: %s", e)

    async def stop(self) -> None:
        """Stop the worker loop. 等待 in-flight 任务最多 30s。"""
        self._running = False
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=self.shutdown_timeout)
            except (TimeoutError, asyncio.CancelledError):
                for task in self._active:
                    task.cancel()
                await asyncio.gather(*self._active, return_exceptions=True)
                for record in self.repository.list_all(status=TaskStatus.RUNNING, limit=100):
                    self.repository.update(record.id, status=TaskStatus.INTERRUPTED)
            self._task = None
        logger.info("TaskWorker stopped")

    async def _loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.exception("Worker tick failed: %s", e)
            if self._active:
                await asyncio.wait(
                    self._active,
                    timeout=self.poll_interval,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            else:
                await asyncio.sleep(self.poll_interval)
        if self._active:
            await asyncio.gather(*self._active, return_exceptions=True)

    async def _tick(self) -> None:
        """Fill the bounded active-task set from pending work."""
        completed = {task for task in self._active if task.done()}
        for task in completed:
            with contextlib.suppress(Exception):
                task.result()
        self._active.difference_update(completed)
        while len(self._active) < self.max_concurrent:
            record = self.repository.reserve_pending_task()
            if record is None:
                break
            self._active.add(asyncio.create_task(self._process(record)))

    async def _process(self, task) -> None:
        """Execute the full pipeline for a task."""
        task_id = task.id
        repo = self.repository
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
            llm_provider = task.llm_provider or "qwen"
            llm_config = _resolve_llm_config(llm_provider)
            ctx = TaskContext(
                task_id=TaskId(task_id),
                config={
                    "url": source,
                    "video_url": task.video_url,
                    "llm_provider": llm_provider,
                    **llm_config,
                    "asr_provider": task.asr_provider or "funasr",
                    "language": "zh",
                    "model_manager": self.models,
                },
            )
            from_node = NodeName(task.rerun_from_node) if task.rerun_from_node else None
            is_srt_task = bool(task.srt_file)
            if is_srt_task:
                if not self.artifacts.exists(task_id, NodeName.TRANSCRIBE.value, "srt_file"):
                    if self.uploads is None:
                        raise Vid2NoteError(
                            "Worker 未配置上传存储",
                            code="UPLOAD_STORE_MISSING",
                            step="transcribe",
                        )
                    uploaded_srt_path = self.uploads.get_path(task.srt_file)
                    if uploaded_srt_path is None:
                        raise Vid2NoteError(
                            f"找不到上传文件: {task.srt_file}",
                            code="UPLOAD_NOT_FOUND",
                            step="transcribe",
                        )
                    self.artifacts.import_file(
                        task_id,
                        NodeName.TRANSCRIBE.value,
                        "srt_file",
                        uploaded_srt_path,
                        move=False,
                    )
                if from_node in {
                    NodeName.DOWNLOAD,
                    NodeName.EXTRACT_AUDIO,
                    NodeName.TRANSCRIBE,
                }:
                    from_node = None
            dag = self._build_dag(start_node=NodeName.ORGANIZE if is_srt_task else None)
            results = await dag.run(ctx, from_node=from_node)

            # Check if any node failed
            failed = [r for r in results if r.status == NodeStatus.FAILED]
            if failed:
                first = failed[0]
                failure = first.error or NodeFailure(
                    code="PIPELINE_NODE_FAILED",
                    message=f"节点 {first.node.value} 失败",
                    user_message="处理步骤失败",
                    retryable=False,
                    step=first.node.value,
                )
                self._handle_failure(task, failure)
                return

            repo.update(
                task_id,
                status=TaskStatus.COMPLETED,
                progress=100,
                current_step="pipeline.completed",
                rerun_from_node=None,
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
            if isinstance(e, Vid2NoteError):
                failure = NodeFailure(
                    code=e.code,
                    message=str(e),
                    user_message=e.user_message,
                    retryable=e.retryable,
                    step=e.step,
                )
            else:
                failure = NodeFailure(
                    code="PIPELINE_RUNTIME_ERROR",
                    message=str(e),
                    user_message="任务处理失败",
                    retryable=False,
                    step="pipeline",
                )
            self._handle_failure(task, failure)

    def _handle_failure(self, task, failure: NodeFailure) -> None:
        attempt = task.retry_count or 0
        retry = failure.retryable and attempt < self.max_retries
        next_status = TaskStatus.PENDING if retry else TaskStatus.FAILED
        next_attempt = attempt + 1 if retry else attempt
        self.repository.update(
            task.id,
            status=next_status,
            retry_count=next_attempt,
            error_message=failure.message,
            error_code=failure.code,
            error_retryable=failure.retryable,
        )
        get_event_bus().publish(
            TaskEvent(
                task_id=task.id,
                event_type="task.retrying" if retry else "task.failed",
                progress=0,
                message=(
                    f"任务失败（第 {next_attempt} 次），稍后重试: {failure.user_message}"
                    if retry
                    else f"任务失败: {failure.user_message}"
                ),
                timestamp=datetime.now().isoformat(),
            )
        )

    def _build_dag(self, start_node: NodeName | None = None) -> PipelineDAG:
        """Build the default pipeline DAG.

        默认全部使用真实节点（download/extract_audio/transcribe/organize/mindmap/cleanup）。
        测试可通过构造参数注入自定义节点。
        """
        if self._nodes is not None:
            return PipelineDAG(self._nodes, self.artifacts)
        nodes = [
            RealDownloadNode(store=self.artifacts, repository=self.repository),
            RealExtractAudioNode(store=self.artifacts, repository=self.repository),
            RealTranscribeNode(store=self.artifacts, repository=self.repository),
            RealOrganizeNode(store=self.artifacts, repository=self.repository),
        ]
        if self.source_registrar is not None:
            nodes.append(
                RealRegisterSourceNode(
                    registrar=self.source_registrar,
                    store=self.artifacts,
                    repository=self.repository,
                )
            )
        if self.vault is not None and self.changesets is not None:
            nodes.append(
                RealProposeWikiChangesNode(
                    store=self.artifacts,
                    vault=self.vault,
                    changesets=self.changesets,
                    repository=self.repository,
                )
            )
        nodes.extend(
            [
                RealMindmapNode(store=self.artifacts, repository=self.repository),
                RealCleanupNode(store=self.artifacts, repository=self.repository),
            ]
        )
        if start_node is not None:
            start_index = next(i for i, node in enumerate(nodes) if node.name is start_node)
            nodes = nodes[start_index:]
        return PipelineDAG(nodes, self.artifacts)
