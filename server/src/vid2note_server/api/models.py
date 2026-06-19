"""模型 API

返回 ASR/LLM 可用的 provider 与模型列表（从 core 工厂读取真实数据）。
"""

from fastapi import APIRouter
from vid2note_core.asr.factory import ASRFactory
from vid2note_core.llm.factory import LLMFactory

from vid2note_server.dependencies import ServicesDependency
from vid2note_server.schemas.common import (
    ERROR_RESPONSES,
    ModelListResponse,
    OllamaStatusResponse,
    ProviderListResponse,
)

router = APIRouter(tags=["models"], responses=ERROR_RESPONSES)


@router.get("/models", response_model=ProviderListResponse)
async def list_models():
    """列出所有可用的 LLM 与 ASR provider"""
    return {
        "llm_providers": LLMFactory.get_available_providers(),
        "asr_providers": ASRFactory.get_available_providers(),
    }


@router.get("/models/asr/available", response_model=ModelListResponse)
async def list_asr_models(services: ServicesDependency):
    """列出本地 ASR 支持的模型档位（FunASR 等）"""
    return {"models": services.models.list_available()}


@router.get("/models/asr/installed", response_model=ModelListResponse)
async def list_installed_asr_models(services: ServicesDependency):
    """列出已下载的本地 ASR 模型"""
    return {"models": services.models.list_installed()}


@router.get("/models/llm/ollama/status", response_model=OllamaStatusResponse)
async def ollama_status():
    """检测本地 Ollama 服务状态"""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                return {"running": True, "models": [m.get("name") for m in data.get("models", [])]}
        return {"running": False, "models": []}
    except Exception:  # noqa: BLE001
        return {"running": False, "models": []}
