"""
配置模型定义
使用 Pydantic 进行配置验证
"""
from typing import Literal, Optional
from pydantic import BaseModel, Field


class QwenConfig(BaseModel):
    """通义千问配置"""
    api_key: str = ""
    model: str = "qwen3.7-plus"
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class GLMConfig(BaseModel):
    """智谱AI配置"""
    api_key: str = ""
    model: str = "glm-5.2"
    base_url: str = "https://open.bigmodel.cn/api/paas/v4/"


class DeepSeekConfig(BaseModel):
    """DeepSeek配置"""
    api_key: str = ""
    model: str = "deepseek-v4-flash"
    base_url: str = "https://api.deepseek.com/v1"


class MoonshotConfig(BaseModel):
    """Moonshot (Kimi)配置"""
    api_key: str = ""
    model: str = "kimi-k2.6"
    base_url: str = "https://api.moonshot.cn/v1"


class BaiduConfig(BaseModel):
    """百度千帆 v2 OpenAI-compatible 配置"""
    api_key: str = ""
    model: str = "ernie-5.0"
    base_url: str = "https://qianfan.baidubce.com/v2"


class DoubaoConfig(BaseModel):
    """字节豆包配置"""
    api_key: str = ""
    model: str = "doubao-seed-2-0-lite-260215"
    base_url: str = "https://ark.cn-beijing.volces.com/api/v3"


class MiniMaxConfig(BaseModel):
    """MiniMax配置"""
    api_key: str = ""
    model: str = "MiniMax-M2.7"
    base_url: str = "https://api.minimaxi.com/v1"


class OllamaConfig(BaseModel):
    """Ollama OpenAI-compatible endpoint configuration."""
    api_key: str = "ollama"
    model: str = "qwen3.5"
    base_url: str = "http://host.docker.internal:11434/v1"


class CustomConfig(BaseModel):
    """自定义 OpenAI-compatible endpoint 配置。"""
    api_key: str = ""
    model: str = ""
    base_url: str = ""


class ProcessingConfig(BaseModel):
    """处理选项配置"""
    extract_images: bool = True
    image_quality: Literal["low", "medium", "high"] = "medium"
    output_format: Literal["markdown"] = "markdown"
    language: Literal["zh", "en"] = "zh"


class AdvancedConfig(BaseModel):
    """高级选项配置"""
    chunk_size: int = 4000
    temperature: float = Field(0.3, ge=0.0, le=1.0)
    max_retries: int = 3


class PDFWatermarksConfig(BaseModel):
    """PDF水印过滤配置"""
    enabled: bool = False
    patterns: list[str] = []


class ServerConfig(BaseModel):
    """服务器配置"""
    port: int = 8765
    host: str = "0.0.0.0"
    debug: bool = False
    temp_dir: str = "/tmp/course-doc-generator"


class AppConfig(BaseModel):
    """应用主配置"""
    version: str = "1.0"
    llm_provider: Literal[
        "qwen", "glm", "deepseek", "moonshot", "baidu", "doubao", "minimax",
        "ollama", "custom"
    ] = "deepseek"
    qwen: Optional[QwenConfig] = None
    glm: Optional[GLMConfig] = None
    deepseek: Optional[DeepSeekConfig] = None
    moonshot: Optional[MoonshotConfig] = None
    baidu: Optional[BaiduConfig] = None
    doubao: Optional[DoubaoConfig] = None
    minimax: Optional[MiniMaxConfig] = None
    ollama: Optional[OllamaConfig] = None
    custom: Optional[CustomConfig] = None
    processing: ProcessingConfig = Field(default_factory=ProcessingConfig)
    advanced: AdvancedConfig = Field(default_factory=AdvancedConfig)
    pdf_watermarks: PDFWatermarksConfig = Field(default_factory=PDFWatermarksConfig)
    default_models: dict = Field(default_factory=dict)  # 各提供商默认模型
    server: ServerConfig = Field(default_factory=ServerConfig)
