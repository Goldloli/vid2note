"""处理 API

提供任务触发与状态/结果查询的便捷入口：
  POST /process/start    —— 创建任务（video_url / video_file 或上传 file_id），立即返回 task_id
  GET  /process/status/{task_id}  —— 查询实时状态（status/progress/current_step/error）
  GET  /process/result/{task_id}  —— 查询产物（从 ArtifactStore 读取 markdown/srt/mindmap 文本）

任务实际执行由后台 TaskWorker 轮询 pending 任务驱动（worker.py）。
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from vid2note_core.events.bus import TaskEvent, get_event_bus
from vid2note_core.types import NodeName, TaskId, TaskStatus

from vid2note_server.dependencies import ServicesDependency
from vid2note_server.schemas.common import ERROR_RESPONSES
from vid2note_server.schemas.process import (
    ResultResponse,
    StartRequest,
    StartResponse,
    StatusResponse,
)

router = APIRouter(tags=["process"], responses=ERROR_RESPONSES)


@router.post("/process/start", response_model=StartResponse)
async def start_process(req: StartRequest, services: ServicesDependency):
    """创建任务并入队。worker 会轮询 pending 任务并执行。"""
    if not any([req.video_url, req.video_file, req.srt_file]):
        raise HTTPException(400, "必须提供 video_url / video_file / srt_file 之一")

    repo = services.tasks
    task_id = TaskId.generate()
    repo.create(
        task_id=task_id,
        status=TaskStatus.PENDING,
        video_url=req.video_url,
        video_file=req.video_file,
        srt_file=req.srt_file,
        srt_original_name=services.uploads.get_name(req.srt_file) if req.srt_file else None,
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
    return StartResponse(task_id=task_id, status=TaskStatus.PENDING.value)


@router.get("/process/status/{task_id}", response_model=StatusResponse)
async def get_status(task_id: str, services: ServicesDependency):
    """查询任务实时状态。"""
    if not TaskId.is_valid(task_id):
        raise HTTPException(400, "非法 task_id")
    repo = services.tasks
    task = repo.get_by_id(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return StatusResponse(
        task_id=task.id,
        status=task.status.value,
        progress=task.progress,
        current_step=task.current_step,
        message=task.message,
        error=task.error_message,
    )


@router.get(
    "/process/result/{task_id}",
    response_model=ResultResponse,
    response_model_exclude_none=True,
)
async def get_result(task_id: str, services: ServicesDependency):
    """查询任务产物。任务未完成时返回已有状态；完成时附带产物文本。"""
    if not TaskId.is_valid(task_id):
        raise HTTPException(400, "非法 task_id")
    repo = services.tasks
    task = repo.get_by_id(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")

    result: dict = {
        "task_id": task.id,
        "status": task.status.value,
        "progress": task.progress,
    }

    # 任务未完成时仅返回状态
    if task.status not in (TaskStatus.COMPLETED, TaskStatus.PARTIAL):
        return result

    # 读取产物（从 ArtifactStore）
    store = services.artifacts
    artifacts: dict[str, str] = {}
    _artifact_map = {
        "markdown": (NodeName.ORGANIZE.value, "markdown_file"),
        "srt": (NodeName.TRANSCRIBE.value, "srt_file"),
        "mindmap": (NodeName.MINDMAP.value, "mindmap_file"),
    }
    for name, (node, key) in _artifact_map.items():
        try:
            data = store.read_artifact(task_id, node, key)
            artifacts[name] = data.decode("utf-8")
        except FileNotFoundError:
            continue
        except Exception:  # noqa: BLE001 - 产物读取失败不影响状态返回
            continue

    result["artifacts"] = artifacts
    return result
