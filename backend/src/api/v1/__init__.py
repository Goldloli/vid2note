"""api.v1 —— v1 路由聚合层(契约 §4)

把 v1 的四组路由(``tasks`` / ``settings`` / ``storage`` / ``health``)聚合到一个
``APIRouter(prefix="/api/v1")`` 下,供 ``src.main`` 注册。

基底旧路由(``api.upload`` / ``process`` / ``config`` / ``queue`` / ``logs``)
已经移除—— v1 路由清单见契约 §4.1。
"""
from fastapi import APIRouter

from .health import router as health_router
from .settings import router as settings_router
from .storage import router as storage_router
from .tasks import router as tasks_router
from .asr import router as asr_router

# v1 主路由(契约 §4.1:统一前缀 ``/api/v1``)
v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(tasks_router)
v1_router.include_router(settings_router)
v1_router.include_router(storage_router)
v1_router.include_router(health_router)
v1_router.include_router(asr_router)

__all__ = ["v1_router"]
