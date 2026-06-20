"""
Stub pipeline nodes for vid2note.
Each node simulates work and publishes events to the EventBus.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from vid2note_core.events.bus import TaskEvent, get_event_bus
from vid2note_core.pipeline.node import PipelineNode
from vid2note_core.storage.task_repo import TaskRepository
from vid2note_core.types import ArtifactRef, NodeName, NodeResult, NodeStatus

if TYPE_CHECKING:
    from vid2note_core.pipeline.context import TaskContext


class _StubNodeMixin:
    name: NodeName
    """Mixin for stub nodes: publishes events and updates DB."""

    def __init__(self, repository: TaskRepository | None = None) -> None:
        self.repository = repository

    async def _publish(
        self,
        task_id: str,
        event_type: str,
        progress: int,
        message: str,
        artifact: str | None = None,
    ) -> None:
        bus = get_event_bus()
        bus.publish(
            TaskEvent(
                task_id=task_id,
                event_type=event_type,
                node_name=self.name.value,
                node_status=NodeStatus.RUNNING.value
                if event_type == "node.started"
                else NodeStatus.COMPLETED.value,
                progress=progress,
                message=message,
                artifact=artifact,
                timestamp=datetime.now().isoformat(),
            )
        )

    def _update_db(
        self, task_id: str, status: NodeStatus, artifacts: list[str] | None = None
    ) -> None:
        if self.repository is not None:
            self.repository.update_node(task_id, self.name.value, status, artifacts=artifacts or [])


class DownloadNode(PipelineNode, _StubNodeMixin):
    name = NodeName.DOWNLOAD
    requires: list[str] = []
    produces: list[str] = ["video_file"]

    async def run(self, ctx: "TaskContext") -> NodeResult:
        task_id = ctx.task_id.value
        self._update_db(task_id, NodeStatus.RUNNING)
        await self._publish(task_id, "node.started", 10, "开始下载视频...")
        await asyncio.sleep(0.5)
        self._update_db(task_id, NodeStatus.COMPLETED, artifacts=["video.mp4"])
        await self._publish(task_id, "node.completed", 25, "视频下载完成", artifact="video.mp4")
        return NodeResult.success(
            node=self.name,
            artifacts=[ArtifactRef(node=self.name, name="video_file")],
            metadata={"video_file": str(Path(ctx.task_id.value) / "video.mp4")},
        )


class ExtractAudioNode(PipelineNode, _StubNodeMixin):
    name = NodeName.EXTRACT_AUDIO
    requires: list[str] = ["video_file"]
    produces: list[str] = ["audio_file"]

    async def run(self, ctx: "TaskContext") -> NodeResult:
        task_id = ctx.task_id.value
        self._update_db(task_id, NodeStatus.RUNNING)
        await self._publish(task_id, "node.started", 30, "提取音频中...")
        await asyncio.sleep(0.5)
        self._update_db(task_id, NodeStatus.COMPLETED, artifacts=["audio.wav"])
        await self._publish(task_id, "node.completed", 45, "音频提取完成", artifact="audio.wav")
        return NodeResult.success(
            node=self.name,
            artifacts=[ArtifactRef(node=self.name, name="audio_file")],
            metadata={"audio_file": str(Path(ctx.task_id.value) / "audio.wav")},
        )


class TranscribeNode(PipelineNode, _StubNodeMixin):
    name = NodeName.TRANSCRIBE
    requires: list[str] = ["audio_file"]
    produces: list[str] = ["srt_file"]

    async def run(self, ctx: "TaskContext") -> NodeResult:
        task_id = ctx.task_id.value
        self._update_db(task_id, NodeStatus.RUNNING)
        await self._publish(task_id, "node.started", 50, "语音识别中...")
        await asyncio.sleep(0.5)
        self._update_db(task_id, NodeStatus.COMPLETED, artifacts=["transcript.srt"])
        await self._publish(
            task_id, "node.completed", 70, "语音识别完成", artifact="transcript.srt"
        )
        return NodeResult.success(
            node=self.name,
            artifacts=[ArtifactRef(node=self.name, name="srt_file")],
            metadata={"srt_file": str(Path(ctx.task_id.value) / "transcript.srt")},
        )


class OrganizeNode(PipelineNode, _StubNodeMixin):
    name = NodeName.ORGANIZE
    requires: list[str] = ["srt_file"]
    produces: list[str] = ["markdown_file"]

    async def run(self, ctx: "TaskContext") -> NodeResult:
        task_id = ctx.task_id.value
        self._update_db(task_id, NodeStatus.RUNNING)
        await self._publish(task_id, "node.started", 75, "LLM 整理笔记中...")
        await asyncio.sleep(0.5)
        self._update_db(task_id, NodeStatus.COMPLETED, artifacts=["note.md"])
        await self._publish(task_id, "node.completed", 95, "笔记整理完成", artifact="note.md")
        return NodeResult.success(
            node=self.name,
            artifacts=[ArtifactRef(node=self.name, name="markdown_file")],
            metadata={"markdown_file": str(Path(ctx.task_id.value) / "note.md")},
        )


class MindmapNode(PipelineNode, _StubNodeMixin):
    name = NodeName.MINDMAP
    requires: list[str] = ["markdown_file"]
    produces: list[str] = ["mindmap_file"]

    async def run(self, ctx: "TaskContext") -> NodeResult:
        task_id = ctx.task_id.value
        self._update_db(task_id, NodeStatus.RUNNING)
        await self._publish(task_id, "node.started", 96, "生成思维导图...")
        await asyncio.sleep(0.3)
        self._update_db(task_id, NodeStatus.COMPLETED, artifacts=["mindmap.xmind"])
        await self._publish(
            task_id, "node.completed", 98, "思维导图生成完成", artifact="mindmap.xmind"
        )
        return NodeResult.success(
            node=self.name,
            artifacts=[ArtifactRef(node=self.name, name="mindmap_file")],
            metadata={"mindmap_file": str(Path(ctx.task_id.value) / "mindmap.xmind")},
        )


class CleanupNode(PipelineNode, _StubNodeMixin):
    name = NodeName.CLEANUP
    requires: list[str] = ["markdown_file"]
    produces: list[str] = []

    async def run(self, ctx: "TaskContext") -> NodeResult:
        task_id = ctx.task_id.value
        self._update_db(task_id, NodeStatus.RUNNING)
        await self._publish(task_id, "node.started", 99, "清理临时文件...")
        await asyncio.sleep(0.2)
        self._update_db(task_id, NodeStatus.COMPLETED)
        await self._publish(task_id, "node.completed", 100, "清理完成")
        return NodeResult.success(node=self.name)
