"""测试 DAG"""

from unittest.mock import AsyncMock

import pytest
from vid2note_core.pipeline.context import TaskContext
from vid2note_core.pipeline.dag import PipelineDAG
from vid2note_core.pipeline.node import PipelineNode
from vid2note_core.storage.artifact_store import ArtifactStore
from vid2note_core.types import NodeName, NodeResult, NodeStatus, TaskId


class MockNode(PipelineNode):
    def __init__(self, name: NodeName, requires=None):
        self.name = name
        self.requires = requires or []
        self._mock_run = AsyncMock(return_value=NodeResult.success(name, []))

    async def run(self, ctx: TaskContext) -> NodeResult:
        return await self._mock_run(ctx)


def test_topology_valid_nodes(tmp_path):
    n1 = MockNode(NodeName.DOWNLOAD)
    n2 = MockNode(NodeName.EXTRACT_AUDIO, requires=["video_file"])
    dag = PipelineDAG([n1, n2], ArtifactStore(tmp_path))
    assert dag is not None


def test_topology_unknown_node_raises(tmp_path):
    """节点名不在 _NODE_ORDER 中应拒绝"""
    n = MockNode(NodeName.DOWNLOAD)
    n.name = "not_a_real_node"  # 伪造未知节点名
    with pytest.raises(ValueError):
        PipelineDAG([n], ArtifactStore(tmp_path))


@pytest.mark.asyncio
async def test_run_all_nodes(tmp_path):
    n1 = MockNode(NodeName.DOWNLOAD)
    n2 = MockNode(NodeName.EXTRACT_AUDIO)
    dag = PipelineDAG([n1, n2], ArtifactStore(tmp_path))
    ctx = TaskContext(task_id=TaskId("task_abcdef012345"))
    results = await dag.run(ctx)
    assert len(results) == 2
    n1._mock_run.assert_called_once()
    n2._mock_run.assert_called_once()


@pytest.mark.asyncio
async def test_run_stops_after_failed_node(tmp_path):
    download = MockNode(NodeName.DOWNLOAD)
    download._mock_run.return_value = NodeResult.failure(
        NodeName.DOWNLOAD, "DOWNLOAD_ERROR", "failed"
    )
    extract = MockNode(NodeName.EXTRACT_AUDIO)
    dag = PipelineDAG([download, extract], ArtifactStore(tmp_path))

    results = await dag.run(TaskContext(task_id=TaskId("task_abcdef012345")))

    assert [result.status for result in results] == [NodeStatus.FAILED]
    extract._mock_run.assert_not_called()


@pytest.mark.asyncio
async def test_resume_reexecutes_node_when_declared_artifact_missing(tmp_path):
    store = ArtifactStore(tmp_path)
    download = MockNode(NodeName.DOWNLOAD)
    download.produces = ["video_file"]
    extract = MockNode(NodeName.EXTRACT_AUDIO)
    extract.produces = ["audio_file"]
    transcribe = MockNode(NodeName.TRANSCRIBE)
    task_id = "task_abcdef012345"
    store.write_artifact(task_id, NodeName.DOWNLOAD.value, "video_file", b"video")
    dag = PipelineDAG([download, extract, transcribe], store)

    await dag.run(TaskContext(task_id=TaskId(task_id)), from_node=NodeName.TRANSCRIBE)

    download._mock_run.assert_not_called()
    extract._mock_run.assert_called_once()
    transcribe._mock_run.assert_called_once()
