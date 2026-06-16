"""Pipeline 节点抽象"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from vid2note_core.types import NodeName, NodeResult

if TYPE_CHECKING:
    from vid2note_core.pipeline.context import TaskContext


class PipelineNode(ABC):
    name: NodeName
    requires: list[str] = []  # artifact key 列表
    produces: list[str] = []  # artifact key 列表

    @abstractmethod
    async def run(self, ctx: "TaskContext") -> NodeResult: ...

    async def resume(self, ctx: "TaskContext") -> NodeResult:
        """默认 resume = run（artifact-driven）"""
        return await self.run(ctx)
