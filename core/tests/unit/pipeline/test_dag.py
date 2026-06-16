"""测试 DAG"""

import pytest
from unittest.mock import AsyncMock
from vid2note_core.pipeline.dag import PipelineDAG
from vid2note_core.pipeline.node import PipelineNode
from vid2note_core.pipeline.context import TaskContext
from vid2note_core.types import NodeName, NodeResult, NodeStatus, TaskId


class MockNode(PipelineNode):
    def __init__(self, name: NodeName, requires=None):
        self.name = name
        self.requires = requires or []
        self._mock_run = AsyncMock(return_value=NodeResult.success(name, []))

    async def run(self, ctx: TaskContext) -> NodeResult:
        return await self._mock_run(ctx)


def test_topology_valid_nodes():
    n1 = MockNode(NodeName.DOWNLOAD)
    n2 = MockNode(NodeName.EXTRACT_AUDIO, requires=["video_file"])
    dag = PipelineDAG([n1, n2])
    assert dag is not None


def test_topology_unknown_node_raises():
    """节点名不在 _NODE_ORDER 中应拒绝"""
    n = MockNode(NodeName.DOWNLOAD)
    n.name = "not_a_real_node"  # 伪造未知节点名
    with pytest.raises(ValueError):
        PipelineDAG([n])


@pytest.mark.asyncio
async def test_run_all_nodes():
    n1 = MockNode(NodeName.DOWNLOAD)
    n2 = MockNode(NodeName.EXTRACT_AUDIO)
    dag = PipelineDAG([n1, n2])
    ctx = TaskContext(task_id=TaskId("task_abcdef012345"))
    results = await dag.run(ctx)
    assert len(results) == 2
    n1._mock_run.assert_called_once()
    n2._mock_run.assert_called_once()
