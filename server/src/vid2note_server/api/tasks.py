"""任务 API"""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from vid2note_core.events.bus import TaskEvent, get_event_bus
from vid2note_core.types import TaskId, TaskStatus

from vid2note_server.dependencies import ServicesDependency

router = APIRouter(tags=["tasks"])


class CreateTaskRequest(BaseModel):
    video_url: str | None = None
    video_file: str | None = None
    pdf_file: str | None = None
    asr_provider: str = "funasr"
    llm_provider: str = "qwen"
    export_mindmap: bool = False


@router.post("/tasks")
async def create_task(req: CreateTaskRequest, services: ServicesDependency):
    repo = services.tasks
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
async def list_tasks(services: ServicesDependency, status: str | None = None, limit: int = 100):
    repo = services.tasks
    tasks = repo.list_all(status=TaskStatus(status) if status else None, limit=limit)
    return {"tasks": tasks, "total": len(tasks)}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, services: ServicesDependency):
    repo = services.tasks
    task = repo.get_by_id(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return task


class RerunRequest(BaseModel):
    from_node: str | None = None


@router.post("/tasks/{task_id}/rerun")
async def rerun_task(task_id: str, services: ServicesDependency, req: RerunRequest | None = None):
    """重跑任务：删除 from_node 下游产物 + 重置节点状态 + 重新入队。

    from_node 为 None 时重跑整个 pipeline；否则只重跑该节点及下游。
    支持请求体 {"from_node": "..."}（前端约定）或空 body 重跑全部。
    """
    if not TaskId.is_valid(task_id):
        raise HTTPException(404, "任务不存在")

    from_node = req.from_node if req else None

    repo = services.tasks
    task = repo.get_by_id(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")

    # 1. 删除 from_node 下游产物（若有）
    if from_node:
        services.artifacts.delete_downstream(task_id, from_node)

    # 2. 重置任务和节点状态 → PENDING
    repo.reset_task_for_rerun(task_id, from_node)

    # 3. 发事件通知前端
    get_event_bus().publish(
        TaskEvent(
            task_id=task_id,
            event_type="task.rerun",
            progress=0,
            message=f"已触发重跑（from {from_node or 'start'}）",
            timestamp=datetime.now().isoformat(),
        )
    )
    return {"task_id": task_id, "status": "pending", "message": "已触发重跑"}
