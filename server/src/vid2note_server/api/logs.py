"""日志 API"""
from fastapi import APIRouter

router = APIRouter(tags=["logs"])

@router.post("/logs/frontend")
async def send_logs():
    return {"message": "日志已接收"}

@router.get("/logs/backend")
async def get_backend_logs():
    return {"logs": []}
