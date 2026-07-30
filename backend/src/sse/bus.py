"""SSE 事件总线(design D10):进程内 pub/sub,供 FastAPI StreamingResponse 订阅。

事件类型(对应 spec task-pipeline):
- node-entered / node-progress / log / node-completed / node-failed
- task-completed / task-failed / task-cancelled
- snapshot:断线重连时先推一次当前状态快照(由调用方从库读出后传入)
每个事件结构:{task_id, event, ts, payload};ts 为 unix 秒。
"""
import asyncio
import json
import time
from typing import Any, AsyncIterator, Dict, Optional, Set

# 终态事件:订阅者收到后正常关闭连接
TERMINAL_EVENTS = {"task-completed", "task-failed", "task-cancelled"}


class SSEBus:
    """单进程内的 SSE 事件总线(个人本地自用,无需跨进程/Redis)。"""

    def __init__(self) -> None:
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, task_id: str) -> asyncio.Queue:
        async with self._lock:
            subs = self._subscribers.setdefault(task_id, set())
            q: asyncio.Queue = asyncio.Queue(maxsize=256)
            subs.add(q)
            return q

    async def unsubscribe(self, task_id: str, q: asyncio.Queue) -> None:
        async with self._lock:
            subs = self._subscribers.get(task_id)
            if subs and q in subs:
                subs.discard(q)
                if not subs:
                    self._subscribers.pop(task_id, None)

    async def publish(
        self, task_id: str, event: str, payload: Optional[Dict[str, Any]] = None
    ) -> None:
        """向某任务的所有订阅者推送一个事件。无订阅者时静默丢弃。"""
        async with self._lock:
            subs = list(self._subscribers.get(task_id, ()))
        if not subs:
            return
        evt = {
            "task_id": task_id,
            "event": event,
            "ts": time.time(),
            "payload": payload or {},
        }
        for q in subs:
            try:
                q.put_nowait(evt)
            except asyncio.QueueFull:
                # 队列满(订阅者消费慢):丢弃以保护生产者,不阻塞 pipeline
                pass

    async def stream(
        self, task_id: str, snapshot: Optional[Dict[str, Any]] = None
    ) -> AsyncIterator[str]:
        """SSE 流生成器。snapshot 非空时先推一次(断线重连快照),再续推实时事件,
        收到终态事件后正常结束。订阅不存在 / 已终态任务:推完 snapshot 即正常关闭。"""
        q = await self.subscribe(task_id)
        try:
            if snapshot:
                yield _format_sse(
                    {
                        "task_id": task_id,
                        "event": "snapshot",
                        "ts": time.time(),
                        "payload": snapshot,
                    }
                )
            while True:
                evt = await q.get()
                yield _format_sse(evt)
                if evt.get("event") in TERMINAL_EVENTS:
                    break
        finally:
            await self.unsubscribe(task_id, q)


def _format_sse(evt: Dict[str, Any]) -> str:
    event_name = str(evt.get("event") or "message").replace("\n", "")
    return (
        f"event: {event_name}\n"
        f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
    )


_bus: Optional[SSEBus] = None


def get_bus() -> SSEBus:
    """单例总线。"""
    global _bus
    if _bus is None:
        _bus = SSEBus()
    return _bus
