"""配置 API"""
from fastapi import APIRouter

router = APIRouter(tags=["config"])

@router.get("/config")
async def get_config():
    return {"llm_provider": "qwen"}

@router.put("/config")
async def update_config():
    return {"message": "配置已更新"}

@router.post("/config/verify")
async def verify_api_key():
    return {"valid": True}
