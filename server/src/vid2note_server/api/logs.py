"""日志 API"""

from fastapi import APIRouter

from vid2note_server.schemas.common import ERROR_RESPONSES, LogsResponse, MessageResponse

router = APIRouter(tags=["logs"], responses=ERROR_RESPONSES)


@router.post("/logs/frontend", response_model=MessageResponse)
async def send_logs():
    return {"message": "日志已接收"}


@router.get("/logs/backend", response_model=LogsResponse)
async def get_backend_logs():
    return {"logs": []}
