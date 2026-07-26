"""
队列管理接口
提供任务队列的查询、取消、删除等操作
"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..core import get_task_queue
from ..models.task import TaskStatus


router = APIRouter(prefix="/api/v1/queue", tags=["queue"])


class TaskInfo(BaseModel):
    """任务信息"""
    id: str
    status: str
    progress: int = Field(0, ge=0, le=100)
    current_step: Optional[str] = None
    message: Optional[str] = None
    title: Optional[str] = None
    download_url: Optional[str] = None
    mindmap_url: Optional[str] = None
    srt_original_name: Optional[str] = None
    txt_original_name: Optional[str] = None
    pdf_original_name: Optional[str] = None
    extract_images: bool = False
    llm_provider: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None


class TaskListResponse(BaseModel):
    """任务列表响应"""
    tasks: List[TaskInfo]
    total: int


class TaskActionResponse(BaseModel):
    """任务操作响应"""
    success: bool
    message: str
    task: Optional[TaskInfo] = None


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    status: Optional[str] = Query(None, description="按状态筛选: pending, processing, completed, failed, cancelled"),
    limit: int = Query(100, ge=1, le=500, description="返回数量限制"),
    offset: int = Query(0, ge=0, description="偏移量")
):
    """
    获取任务列表

    支持按状态筛选和分页
    """
    task_queue = get_task_queue()

    # 转换状态字符串为枚举
    status_filter = None
    if status:
        try:
            status_filter = TaskStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的状态值: {status}")

    # 获取任务列表
    tasks = task_queue.list_tasks(status=status_filter, limit=limit)

    # 转换为响应格式
    task_infos = []
    for task in tasks:
        task_infos.append(TaskInfo(
            id=task.id,
            status=task.status.value,
            progress=task.progress,
            current_step=task.current_step,
            message=task.message,
            title=task.title,
            download_url=task.download_url,
            mindmap_url=task.mindmap_url,
            srt_original_name=task.srt_original_name,
            txt_original_name=task.txt_original_name,
            pdf_original_name=task.pdf_original_name,
            extract_images=task.extract_images,
            llm_provider=task.llm_provider,
            created_at=task.created_at.isoformat() if task.created_at else None,
            updated_at=task.updated_at.isoformat() if task.updated_at else None,
            completed_at=task.completed_at.isoformat() if task.completed_at else None,
            error_message=task.error_message
        ))

    return TaskListResponse(
        tasks=task_infos,
        total=len(task_infos)
    )


@router.get("/tasks/{task_id}", response_model=TaskInfo)
async def get_task(task_id: str):
    """
    获取单个任务详情
    """
    task_queue = get_task_queue()
    task = task_queue.get_task_status(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return TaskInfo(
        id=task.id,
        status=task.status.value,
        progress=task.progress,
        current_step=task.current_step,
        message=task.message,
        title=task.title,
        download_url=task.download_url,
        mindmap_url=task.mindmap_url,
        srt_original_name=task.srt_original_name,
        txt_original_name=task.txt_original_name,
        pdf_original_name=task.pdf_original_name,
        extract_images=task.extract_images,
        llm_provider=task.llm_provider,
        created_at=task.created_at.isoformat() if task.created_at else None,
        updated_at=task.updated_at.isoformat() if task.updated_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        error_message=task.error_message
    )


@router.post("/tasks/{task_id}/cancel", response_model=TaskActionResponse)
async def cancel_task(task_id: str):
    """
    取消任务

    只能取消 pending 或 processing 状态的任务
    """
    task_queue = get_task_queue()
    task = task_queue.get_task_status(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status not in [TaskStatus.PENDING, TaskStatus.PROCESSING]:
        raise HTTPException(
            status_code=400,
            detail=f"无法取消状态为 '{task.status.value}' 的任务"
        )

    success = task_queue.cancel_task(task_id)

    if success:
        # 获取更新后的任务
        updated_task = task_queue.get_task_status(task_id)
        return TaskActionResponse(
            success=True,
            message="任务已取消",
            task=TaskInfo(
                id=updated_task.id,
                status=updated_task.status.value,
                progress=updated_task.progress,
                current_step=updated_task.current_step,
                message=updated_task.message,
                title=updated_task.title,
                download_url=updated_task.download_url,
                srt_original_name=updated_task.srt_original_name,
                txt_original_name=updated_task.txt_original_name,
                pdf_original_name=updated_task.pdf_original_name,
                extract_images=updated_task.extract_images,
                llm_provider=updated_task.llm_provider,
                created_at=updated_task.created_at.isoformat() if updated_task.created_at else None,
                updated_at=updated_task.updated_at.isoformat() if updated_task.updated_at else None,
                completed_at=updated_task.completed_at.isoformat() if updated_task.completed_at else None,
                error_message=updated_task.error_message
            )
        )
    else:
        raise HTTPException(status_code=500, detail="取消任务失败")


@router.delete("/tasks/{task_id}", response_model=TaskActionResponse)
async def delete_task(task_id: str):
    """
    删除任务

    会从数据库中永久删除任务记录
    """
    task_queue = get_task_queue()
    task = task_queue.get_task_status(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 如果任务正在处理中，先取消
    if task.status == TaskStatus.PROCESSING:
        task_queue.cancel_task(task_id)

    success = task_queue.delete_task(task_id)

    if success:
        return TaskActionResponse(
            success=True,
            message="任务已删除"
        )
    else:
        raise HTTPException(status_code=500, detail="删除任务失败")


@router.get("/stats")
async def get_queue_stats():
    """
    获取队列统计信息
    """
    task_queue = get_task_queue()

    from ..db import TaskRepository
    from ..models.task import TaskStatus

    repository = TaskRepository()

    # 获取队列状态（包含 max_queue_size 和 active_count）
    queue_status = task_queue.get_queue_status()

    stats = {
        "pending": repository.count_by_status(TaskStatus.PENDING),
        "processing": repository.count_by_status(TaskStatus.PROCESSING),
        "completed": repository.count_by_status(TaskStatus.COMPLETED),
        "failed": repository.count_by_status(TaskStatus.FAILED),
        "cancelled": repository.count_by_status(TaskStatus.CANCELLED),
        "max_concurrent": task_queue.max_concurrent,
        "max_queue_size": queue_status["max_queue_size"],
        "active_count": queue_status["active_count"],
        "available_slots": queue_status["available_slots"],
        "is_full": queue_status["is_full"]
    }

    return stats


@router.delete("/tasks", response_model=TaskActionResponse)
async def clear_completed_tasks():
    """
    清空所有已完成的任务（包括已完成和失败的）

    这会从数据库中永久删除所有状态为 completed 或 failed 的任务
    """
    task_queue = get_task_queue()
    deleted_count = task_queue.clear_completed_tasks()

    return TaskActionResponse(
        success=True,
        message=f"已清空 {deleted_count} 个任务",
        task=None
    )
