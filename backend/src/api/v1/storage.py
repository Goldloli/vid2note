"""``GET /api/v1/storage/stats`` —— 存储用量统计(契约 §4.1)。

委托 :func:`src.retention.storage_stats`,返回五类产物占用、temp 占用与占用最高任务。
"""
from fastapi import APIRouter

from src.retention import storage_stats
from src.runtime.task_service import get_task_service

router = APIRouter(prefix="/storage", tags=["storage"])


@router.get("/stats")
async def storage_stats_endpoint():
    """存储用量统计。"""
    data_root = get_task_service().data_root
    return storage_stats(data_root)
