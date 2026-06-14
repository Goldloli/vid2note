"""SSE 事件推送"""
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import asyncio

router = APIRouter(tags=["events"])

@router.get("/tasks/{task_id}/events")
async def task_events(task_id: str):
    async def event_generator():
        # TODO: 从任务状态队列读取事件
        yield f"data: {{'type': 'task.started'}}\n\n"
        await asyncio.sleep(1)
        yield f"data: {{'type': 'node.completed', 'node': 'download'}}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
