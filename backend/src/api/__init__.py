"""
API 路由模块
"""
from fastapi import APIRouter

from .upload import router as upload_router
from .process import router as process_router
from .config import router as config_router
from .queue import router as queue_router
from .logs import router as logs_router

# 主路由
api_router = APIRouter()

# 注册子路由
api_router.include_router(upload_router)
api_router.include_router(process_router)
api_router.include_router(config_router)
api_router.include_router(queue_router)
api_router.include_router(logs_router)

__all__ = ["api_router"]
