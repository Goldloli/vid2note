"""任务 API"""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from vid2note_core.events.bus import TaskEvent, get_event_bus
from vid2note_core.storage.task_repo import TaskRepository
from vid2note_core.types import TaskId, TaskStatus

router = APIRouter(tags=["tasks"])


class CreateTaskRequest(BaseModel):
    video_url: str | None = None
    video_file: str | None = None
    pdf_file: str | None = None
    asr_provider: str = "asrtools-b"
    llm_provider: str = "qwen"
    export_mindmap: bool = False


@router.post("/tasks")
async def create_task(req: CreateTaskRequest):
    repo = TaskRepository()
    task_id = TaskId.generate()
    repo.create(
        task_id=task_id,
        status=TaskStatus.PENDING,
        video_url=req.video_url,
        video_file=req.video_file,
        pdf_file=req.pdf_file,
        asr_provider=req.asr_provider,
        llm_provider=req.llm_provider,
        export_mindmap=req.export_mindmap,
    )
    get_event_bus().publish(
        TaskEvent(
            task_id=task_id,
            event_type="task.created",
            progress=0,
            message="任务已创建，等待处理",
            timestamp=datetime.now().isoformat(),
        )
    )
    return {"task_id": task_id, "status": "pending"}


@router.get("/tasks")
async def list_tasks(status: str | None = None, limit: int = 100):
    repo = TaskRepository()
    tasks = repo.list_all(status=TaskStatus(status) if status else None, limit=limit)
    return {"tasks": tasks, "total": len(tasks)}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    repo = TaskRepository()
    task = repo.get_by_id(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return task


@router.post("/tasks/{task_id}/rerun")
async def rerun_task(task_id: str, from_node: str | None = None):
    repo = TaskRepository()
    task = repo.get_by_id(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    repo.update(task_id, status=TaskStatus.PENDING)
    return {"task_id": task_id, "message": "已触发重跑"}
