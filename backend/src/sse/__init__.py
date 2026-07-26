"""SSE 事件总线(design D10)。
进程内 pub/sub,每任务一个 asyncio.Queue 池。
节点状态「先落库再推 SSE」由调用方(pipeline)保证,本模块只负责把事件推给订阅者。
"""
from .bus import SSEBus, get_bus, TERMINAL_EVENTS

__all__ = ["SSEBus", "get_bus", "TERMINAL_EVENTS"]
