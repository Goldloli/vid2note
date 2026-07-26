"""
配置管理接口
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import config_manager, PDFWatermarksConfig
from ..llm import LLMFactory


router = APIRouter(prefix="/api/v1/config", tags=["config"])


class LLMConfigRequest(BaseModel):
    """LLM配置请求"""
    provider: str
    api_key: str
    model: str
    base_url: Optional[str] = None


class LLMConfigResponse(BaseModel):
    """LLM配置响应"""
    provider: str
    model: str
    base_url: Optional[str] = None


class PDFWatermarksConfig(BaseModel):
    """PDF水印配置"""
    enabled: bool = False
    patterns: List[str] = []


class ConfigResponse(BaseModel):
    """配置响应"""
    llm_provider: str
    available_providers: List[str]
    qwen: Optional[dict] = None
    glm: Optional[dict] = None
    deepseek: Optional[dict] = None
    moonshot: Optional[dict] = None
    baidu: Optional[dict] = None
    doubao: Optional[dict] = None
    minimax: Optional[dict] = None
    processing: dict
    advanced: dict
    pdf_watermarks: dict
    default_models: dict


class VerifyKeyRequest(BaseModel):
    """验证API Key请求"""
    provider: str
    api_key: str


class VerifyKeyResponse(BaseModel):
    """验证API Key响应"""
    valid: bool
    message: str
    balance: Optional[float] = None


@router.get("", response_model=ConfigResponse)
async def get_config():
    """
    获取当前配置
    """
    config = config_manager.load()

    return ConfigResponse(
        llm_provider=config.llm_provider,
        available_providers=LLMFactory.get_available_providers(),
        qwen=config.qwen.model_dump() if config.qwen else None,
        glm=config.glm.model_dump() if config.glm else None,
        deepseek=config.deepseek.model_dump() if config.deepseek else None,
        moonshot=config.moonshot.model_dump() if config.moonshot else None,
        baidu=config.baidu.model_dump() if config.baidu else None,
        doubao=config.doubao.model_dump() if config.doubao else None,
        minimax=config.minimax.model_dump() if config.minimax else None,
        processing={
            "extract_images": config.processing.extract_images,
            "image_quality": config.processing.image_quality,
            "output_format": config.processing.output_format,
            "language": config.processing.language
        },
        advanced={
            "chunk_size": config.advanced.chunk_size,
            "temperature": config.advanced.temperature,
            "max_retries": config.advanced.max_retries
        },
        pdf_watermarks={
            "enabled": config.pdf_watermarks.enabled,
            "patterns": config.pdf_watermarks.patterns
        },
        default_models=config.default_models
    )


@router.put("")
async def update_config(config_update: dict):
    """
    更新配置
    """
    try:
        config = config_manager.load()
        
        # 更新LLM提供商
        if 'llm_provider' in config_update:
            if config_update['llm_provider'] not in LLMFactory.get_available_providers():
                raise HTTPException(
                    status_code=400,
                    detail=f"不支持的LLM提供商: {config_update['llm_provider']}"
                )
            config.llm_provider = config_update['llm_provider']
        
        # 更新Qwen配置
        if 'qwen' in config_update:
            from ..config import QwenConfig
            config.qwen = QwenConfig(**config_update['qwen'])
        
        # 更新GLM配置
        if 'glm' in config_update:
            from ..config import GLMConfig
            config.glm = GLMConfig(**config_update['glm'])

        # 更新DeepSeek配置
        if 'deepseek' in config_update:
            from ..config import DeepSeekConfig
            config.deepseek = DeepSeekConfig(**config_update['deepseek'])

        # 更新Moonshot配置
        if 'moonshot' in config_update:
            from ..config import MoonshotConfig
            config.moonshot = MoonshotConfig(**config_update['moonshot'])

        # 更新百度配置
        if 'baidu' in config_update:
            from ..config import BaiduConfig
            config.baidu = BaiduConfig(**config_update['baidu'])

        # 更新豆包配置
        if 'doubao' in config_update:
            from ..config import DoubaoConfig
            config.doubao = DoubaoConfig(**config_update['doubao'])

        # 更新MiniMax配置
        if 'minimax' in config_update:
            from ..config import MiniMaxConfig
            config.minimax = MiniMaxConfig(**config_update['minimax'])

        # 更新处理选项
        if 'processing' in config_update:
            for key, value in config_update['processing'].items():
                if hasattr(config.processing, key):
                    setattr(config.processing, key, value)

        # 更新PDF水印配置
        if 'pdf_watermarks' in config_update:
            from ..config import PDFWatermarksConfig
            pdf_watermarks_data = config_update['pdf_watermarks']
            config.pdf_watermarks = PDFWatermarksConfig(
                enabled=pdf_watermarks_data.get('enabled', False),
                patterns=pdf_watermarks_data.get('patterns', [])
            )

        # 更新各提供商默认模型配置
        if 'default_models' in config_update:
            config.default_models = config_update['default_models']

        config_manager.save(config)
        
        return {
            "success": True,
            "message": "配置已保存"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存配置失败: {str(e)}")


@router.post("/verify", response_model=VerifyKeyResponse)
async def verify_api_key(request: VerifyKeyRequest):
    """
    验证API Key
    """
    try:
        provider = request.provider.lower()
        
        if provider not in LLMFactory.get_available_providers():
            return VerifyKeyResponse(
                valid=False,
                message=f"不支持的提供商: {provider}"
            )
        
        # 尝试创建LLM实例并验证
        # 这里可以实现实际的验证逻辑
        result = config_manager.verify_api_key(provider, request.api_key)
        
        return VerifyKeyResponse(**result)
        
    except Exception as e:
        return VerifyKeyResponse(
            valid=False,
            message=f"验证失败: {str(e)}"
        )


@router.get("/models")
async def get_available_models():
    """
    获取可用的模型列表
    """
    return {
        "qwen": [
            {"id": "qwen-turbo", "name": "Qwen Turbo", "description": "快速处理，性价比高"},
            {"id": "qwen-plus", "name": "Qwen Plus", "description": "标准处理，质量均衡"},
            {"id": "qwen-max", "name": "Qwen Max", "description": "高质量，复杂内容"}
        ],
        "glm": [
            {"id": "glm-4-flash", "name": "GLM-4-Flash", "description": "免费额度大"},
            {"id": "glm-4-air", "name": "GLM-4-Air", "description": "质量与速度平衡"},
            {"id": "glm-4", "name": "GLM-4", "description": "长文本支持好"},
            {"id": "glm-5", "name": "GLM-5", "description": "综合能力最强"}
        ],
        "deepseek": [
            {"id": "deepseek-chat", "name": "DeepSeek Chat", "description": "通用对话，性价比高"},
            {"id": "deepseek-coder", "name": "DeepSeek Coder", "description": "代码专用模型"},
            {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner", "description": "推理能力强"}
        ],
        "moonshot": [
            {"id": "moonshot-v1-8k", "name": "Kimi K1 8K", "description": "快速响应"},
            {"id": "moonshot-v1-32k", "name": "Kimi K1 32K", "description": "长文档处理"},
            {"id": "moonshot-v1-128k", "name": "Kimi K1 128K", "description": "超长上下文"}
        ],
        "baidu": [
            {"id": "ernie-bot-4", "name": "文心一言4.0", "description": "高质量理解"},
            {"id": "ernie-bot", "name": "文心一言", "description": "标准版"},
            {"id": "ernie-bot-turbo", "name": "文心一言Turbo", "description": "快速响应"},
            {"id": "ernie-speed", "name": "文心Speed", "description": "极速版"},
            {"id": "ernie-lite", "name": "文心Lite", "description": "轻量版"}
        ],
        "doubao": [
            {"id": "doubao-pro-4k", "name": "豆包Pro 4K", "description": "专业版短文本"},
            {"id": "doubao-pro-32k", "name": "豆包Pro 32K", "description": "专业版长文本"},
            {"id": "doubao-pro-128k", "name": "豆包Pro 128K", "description": "专业版超长文本"},
            {"id": "doubao-lite-4k", "name": "豆包Lite 4K", "description": "轻量版"}
        ],
        "minimax": [
            {"id": "abab6.5-chat", "name": "abab6.5", "description": "综合能力均衡"},
            {"id": "abab6.5s-chat", "name": "abab6.5s", "description": "快速响应"},
            {"id": "abab6-chat", "name": "abab6", "description": "长文本支持"}
        ]
    }
