"""DAG 编排"""
from typing import List, Optional
from vid2note_core.types import NodeName, NodeResult, NodeStatus
from vid2note_core.pipeline.node import PipelineNode
from vid2note_core.storage.artifact_store import ArtifactStore
from vid2note_core.errors import PipelineUpstreamMissing, PipelineCircularDependency


# 节点拓扑顺序
_NODE_ORDER = [
    NodeName.DOWNLOAD,
    NodeName.EXTRACT_AUDIO,
    NodeName.TRANSCRIBE,
    NodeName.ORGANIZE,
    NodeName.MINDMAP,
    NodeName.CLEANUP,
]


class PipelineDAG:
    def __init__(self, nodes: List[PipelineNode]):
        self.nodes = {n.name: n for n in nodes}
        self._validate_topology()

    def _validate_topology(self) -> None:
        """检查循环依赖"""
        visited = set()
        rec_stack = set()

        def dfs(node_name: NodeName) -> bool:
            visited.add(node_name)
            rec_stack.add(node_name)
            node = self.nodes[node_name]
            for req in node.requires:
                req_name = NodeName(req)
                if req_name not in visited:
                    if dfs(req_name):
                        return True
                elif req_name in rec_stack:
                    return True
            rec_stack.remove(node_name)
            return False

        for name in self.nodes:
            if name not in visited:
                if dfs(name):
                    raise PipelineCircularDependency()

    async def run(self, ctx: "TaskContext", from_node: Optional[NodeName] = None) -> List[NodeResult]:
        """运行 pipeline，可选从指定节点开始"""
        results = []
        store = ArtifactStore()
        skip_until = from_node is not None

        for node in self._ordered_nodes():
            if skip_until:
                if node.name == from_node:
                    skip_until = False
                else:
                    # 检查上游产物是否存在
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

    def _ordered_nodes(self) -> List[PipelineNode]:
        """拓扑排序"""
        return [self.nodes[n] for n in _NODE_ORDER if n in self.nodes]
