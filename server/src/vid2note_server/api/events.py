"""SSE 事件推送"""

import asyncio

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from vid2note_core.events.bus import get_event_bus

router = APIRouter(tags=["events"])


async def event_stream(task_id: str):
    bus = get_event_bus()
    queue = bus.subscribe(task_id)
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield event.to_sse_payload()
            except TimeoutError:
                yield ":keep-alive\n\n"
    finally:
        bus.unsubscribe(task_id, queue)


@router.get("/tasks/{task_id}/events")
async def task_events(task_id: str):
    return StreamingResponse(
        event_stream(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
