"""Pipeline 节点抽象"""
from abc import ABC, abstractmethod
from vid2note_core.types import NodeName, NodeResult


class PipelineNode(ABC):
    name: NodeName
    requires: list[str] = []   # artifact key 列表
    produces: list[str] = []   # artifact key 列表

    @abstractmethod
    async def run(self, ctx: "TaskContext") -> NodeResult:
        ...

    async def resume(self, ctx: "TaskContext") -> NodeResult:
        """默认 resume = run（artifact-driven）"""
        return await self.run(ctx)
