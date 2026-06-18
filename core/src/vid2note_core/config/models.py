"""配置模型定义"""

from typing import Literal

from pydantic import BaseModel, Field


class QwenConfig(BaseModel):
    """通义千问配置"""

    api_key: str = ""
    model: str = "qwen-turbo"
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class GLMConfig(BaseModel):
    """智谱AI配置"""

    api_key: str = ""
    model: str = "glm-4-flash"
    base_url: str = "https://open.bigmodel.cn/api/paas/v4/"


class DeepSeekConfig(BaseModel):
    """DeepSeek配置"""

    api_key: str = ""
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com/v1"


class MoonshotConfig(BaseModel):
    """Moonshot (Kimi)配置"""

    api_key: str = ""
    model: str = "moonshot-v1-8k"
    base_url: str = "https://api.moonshot.cn/v1"


class BaiduConfig(BaseModel):
    """百度文心一言配置"""

    api_key: str = ""
    secret_key: str = ""
    model: str = "ernie-bot-4"
    base_url: str = "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop"


class DoubaoConfig(BaseModel):
    """字节豆包配置"""

    api_key: str = ""
    model: str = "doubao-pro-4k"
    base_url: str = "https://ark.cn-beijing.volces.com/api/v3"


class MiniMaxConfig(BaseModel):
    """MiniMax配置"""

    api_key: str = ""
    group_id: str = ""
    model: str = "abab6.5-chat"
    base_url: str = "https://api.minimax.chat/v1"


class OllamaConfig(BaseModel):
    """Ollama 本地配置"""

    host: str = "http://localhost:11434"
    model: str = "llama3"


class ProcessingConfig(BaseModel):
    """处理选项配置"""

    extract_images: bool = True
    image_quality: Literal["low", "medium", "high"] = "medium"
    output_format: Literal["markdown"] = "markdown"
    language: Literal["zh", "en"] = "zh"
    mindmap_format: Literal["mermaid", "outline"] = "mermaid"


class AdvancedConfig(BaseModel):
    """高级选项配置"""

    chunk_size: int = 4000
    temperature: float = Field(0.3, ge=0.0, le=1.0)
    max_retries: int = 3


class PDFWatermarksConfig(BaseModel):
    """PDF水印过滤配置"""

    enabled: bool = False
    patterns: list[str] = []


class RetentionConfig(BaseModel):
    """文件保留策略"""

    keep_video: bool = False
    keep_audio: bool = False
    keep_srt: bool = True
    keep_markdown: bool = True
    keep_mindmap: bool = True
    auto_cleanup_after_days: int = 7


class ASRConfig(BaseModel):
    """ASR 配置"""

    provider: str = "asrtools-b"
    local_model: str = "funasr-paraformer-small"


class ServerConfig(BaseModel):
    """服务器配置"""

    port: int = 8765
    host: str = "0.0.0.0"
    debug: bool = False
    temp_dir: str = "/tmp/course-doc-generator"


class AppConfig(BaseModel):
    """应用主配置"""

    version: str = "0.1.0"
    llm_provider: Literal[
        "qwen", "glm", "deepseek", "moonshot", "baidu", "doubao", "minimax", "ollama"
    ] = "qwen"
    qwen: QwenConfig | None = None
    glm: GLMConfig | None = None
    deepseek: DeepSeekConfig | None = None
    moonshot: MoonshotConfig | None = None
    baidu: BaiduConfig | None = None
    doubao: DoubaoConfig | None = None
    minimax: MiniMaxConfig | None = None
    ollama: OllamaConfig | None = None
    processing: ProcessingConfig = ProcessingConfig()
    advanced: AdvancedConfig = AdvancedConfig(temperature=0.3)
    pdf_watermarks: PDFWatermarksConfig = PDFWatermarksConfig()
    default_models: dict = {}
    server: ServerConfig = ServerConfig()
    retention: RetentionConfig = RetentionConfig()
    asr: ASRConfig = ASRConfig()
    run_mode: str = "dev"
