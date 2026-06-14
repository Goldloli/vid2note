"""任务 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from vid2note_core.storage.task_repo import TaskRepository
from vid2note_core.types import TaskStatus

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
    # TODO: 生成 task_id，创建任务
    return {"task_id": "task_xxx", "status": "pending"}

@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    repo = TaskRepository()
    task = repo.get_by_id(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return task

@router.post("/tasks/{task_id}/rerun")
async def rerun_task(task_id: str, from_node: str | None = None):
    # TODO: 触发重跑
    return {"task_id": task_id, "message": "已触发重跑"}
