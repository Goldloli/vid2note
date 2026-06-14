"""模型 API"""
from fastapi import APIRouter

router = APIRouter(tags=["models"])

@router.get("/models")
async def list_models():
    return {"models": ["qwen-turbo", "glm-4-flash"]}
