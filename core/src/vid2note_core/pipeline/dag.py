"""DAG 编排"""

from typing import TYPE_CHECKING

from vid2note_core.errors import PipelineUpstreamMissing
from vid2note_core.pipeline.node import PipelineNode
from vid2note_core.storage.artifact_store import ArtifactStore
from vid2note_core.types import NodeName, NodeResult

if TYPE_CHECKING:
    from vid2note_core.pipeline.context import TaskContext

# 节点拓扑顺序（流水线是固定线性 DAG，顺序在此声明）
_NODE_ORDER = [
    NodeName.DOWNLOAD,
    NodeName.EXTRACT_AUDIO,
    NodeName.TRANSCRIBE,
    NodeName.ORGANIZE,
    NodeName.MINDMAP,
    NodeName.CLEANUP,
]


class PipelineDAG:
    """线性流水线编排器。

    requires 字段记录的是**上游 artifact key**（如 "video_file"），仅用于
    resume 时的产物存在性检查；拓扑顺序由 _NODE_ORDER 决定（固定线性 DAG，
    不存在循环）。因此本类不做按 NodeName 的循环检测。
    """

    def __init__(self, nodes: list[PipelineNode], artifacts: ArtifactStore):
        self.nodes = {n.name: n for n in nodes}
        self.artifacts = artifacts
        self._validate_known_nodes()

    def _validate_known_nodes(self) -> None:
        """所有节点必须出现在 _NODE_ORDER 中（保证可确定拓扑顺序）。"""
        for name in self.nodes:
            if name not in _NODE_ORDER:
                raise ValueError(f"未知节点 {name!r}，不在拓扑顺序中")

    async def run(self, ctx: "TaskContext", from_node: NodeName | None = None) -> list[NodeResult]:
        """运行 pipeline，可选从指定节点开始（断点续传）"""
        results = []
        store = self.artifacts
        skip_until = from_node is not None

        for node in self._ordered_nodes():
            if skip_until:
                if node.name == from_node:
                    skip_until = False
                else:
                    # 检查上游产物是否存在（resume 场景）
                    missing = []
                    for req in node.requires:
                        if not store.exists(ctx.task_id.value, node.name.value, req):
                            missing.append(req)
                    if missing:
                        raise PipelineUpstreamMissing(node.name.value, missing)
                    continue

            result = await node.run(ctx)
            results.append(result)

        return results

    def _ordered_nodes(self) -> list[PipelineNode]:
        """拓扑排序"""
        return [self.nodes[n] for n in _NODE_ORDER if n in self.nodes]
