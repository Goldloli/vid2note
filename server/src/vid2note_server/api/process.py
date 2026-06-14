"""处理 API"""
from fastapi import APIRouter

router = APIRouter(tags=["process"])

@router.post("/process/start")
async def start_process():
    return {"message": "处理开始"}

@router.get("/process/status/{task_id}")
async def get_status(task_id: str):
    return {"task_id": task_id, "status": "pending"}
