"""
Stub pipeline nodes tests
"""

import pytest
from vid2note_core.pipeline.context import TaskContext
from vid2note_core.pipeline.nodes import (
    CleanupNode,
    DownloadNode,
    ExtractAudioNode,
    MindmapNode,
    OrganizeNode,
    TranscribeNode,
)
from vid2note_core.types import NodeStatus, TaskId


@pytest.fixture
def ctx():
    return TaskContext(task_id=TaskId("task_123456789abc"))


@pytest.mark.asyncio
async def test_download_node(ctx):
    node = DownloadNode()
    result = await node.run(ctx)
    assert result.status == NodeStatus.COMPLETED
    assert result.node.value == "download"


@pytest.mark.asyncio
async def test_extract_audio_node(ctx):
    node = ExtractAudioNode()
    result = await node.run(ctx)
    assert result.status == NodeStatus.COMPLETED
    assert result.node.value == "extract_audio"


@pytest.mark.asyncio
async def test_transcribe_node(ctx):
    node = TranscribeNode()
    result = await node.run(ctx)
    assert result.status == NodeStatus.COMPLETED
    assert result.node.value == "transcribe"


@pytest.mark.asyncio
async def test_organize_node(ctx):
    node = OrganizeNode()
    result = await node.run(ctx)
    assert result.status == NodeStatus.COMPLETED
    assert result.node.value == "organize"


@pytest.mark.asyncio
async def test_mindmap_node(ctx):
    node = MindmapNode()
    result = await node.run(ctx)
    assert result.status == NodeStatus.COMPLETED
    assert result.node.value == "mindmap"


@pytest.mark.asyncio
async def test_cleanup_node(ctx):
    node = CleanupNode()
    result = await node.run(ctx)
    assert result.status == NodeStatus.COMPLETED
    assert result.node.value == "cleanup"
