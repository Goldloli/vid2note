"""
配置管理器
负责配置的加载、保存和管理
所有配置存储在 config/config.yaml 文件中
"""
import os
import yaml
from pathlib import Path
from typing import Optional

from .models import (
    AppConfig, QwenConfig, GLMConfig, DeepSeekConfig,
    MoonshotConfig, BaiduConfig, DoubaoConfig, MiniMaxConfig,
    ServerConfig
)


class ConfigManager:
    """配置管理器"""

    # 项目根目录下的config文件夹（支持环境变量覆盖，方便容器化部署）
    _DEFAULT_CONFIG_DIR = Path(__file__).parent.parent.parent.parent / "config"
    CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", str(_DEFAULT_CONFIG_DIR)))
    CONFIG_FILE = CONFIG_DIR / "config.yaml"

    def __init__(self):
        self._config: Optional[AppConfig] = None
        self._config_mtime: float = 0  # 配置文件最后修改时间

    def load(self) -> AppConfig:
        """从配置文件加载，自动检测文件修改"""
        # 检查配置文件是否被修改
        try:
            current_mtime = self.CONFIG_FILE.stat().st_mtime
            if self._config is not None and current_mtime == self._config_mtime:
                return self._config
            self._config_mtime = current_mtime
        except FileNotFoundError:
            pass

        # 尝试从文件加载
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    self._config = AppConfig(**data)
            except Exception as e:
                print(f"[Config] 加载配置文件失败: {e}")
                if self._config is None:
                    self._config = self._create_default()
        else:
            # 创建默认配置
            self._config = self._create_default()
            # 保存默认配置到文件
            self.save(self._config)

        # 用环境变量覆盖（容器化部署时使用）
        self._apply_env_overrides(self._config)

        return self._config

    def _apply_env_overrides(self, config: AppConfig):
        """从环境变量覆盖配置（Docker 部署用）

        支持的环境变量：
        - LLM_PROVIDER: 默认 LLM 提供商
        - QWEN_API_KEY / QWEN_MODEL / QWEN_BASE_URL
        - GLM_API_KEY / GLM_MODEL / GLM_BASE_URL
        - 同理 DEEPSEEK_*, MOONSHOT_*, BAIDU_*, DOUBAO_*, MINIMAX_*
        - SERVER_PORT / SERVER_HOST / DEBUG
        """
        # 默认提供商
        if os.environ.get("LLM_PROVIDER"):
            config.llm_provider = os.environ["LLM_PROVIDER"]

        # 通用：把每个 provider 的覆盖项映射到对应字段
        provider_fields = {
            "qwen": ("QWEN", config.qwen),
            "glm": ("GLM", config.glm),
            "deepseek": ("DEEPSEEK", config.deepseek),
            "moonshot": ("MOONSHOT", config.moonshot),
            "baidu": ("BAIDU", config.baidu),
            "doubao": ("DOUBAO", config.doubao),
            "minimax": ("MINIMAX", config.minimax),
        }

        for name, (prefix, prov_cfg) in provider_fields.items():
            api_key = os.environ.get(f"{prefix}_API_KEY")
            model = os.environ.get(f"{prefix}_MODEL")
            base_url = os.environ.get(f"{prefix}_BASE_URL")
            if any([api_key, model, base_url]):
                if prov_cfg is None:
                    # 用空配置初始化，再用 env 填充
                    defaults = {
                        "qwen": QwenConfig,
                        "glm": GLMConfig,
                        "deepseek": DeepSeekConfig,
                        "moonshot": MoonshotConfig,
                        "baidu": BaiduConfig,
                        "doubao": DoubaoConfig,
                        "minimax": MiniMaxConfig,
                    }
                    prov_cfg = defaults[name]()
                    setattr(config, name, prov_cfg)
                if api_key is not None:
                    prov_cfg.api_key = api_key
                if model is not None:
                    prov_cfg.model = model
                if base_url is not None:
                    prov_cfg.base_url = base_url
                # 百度/MiniMax 特有字段
                if name == "baidu":
                    sk = os.environ.get("BAIDU_SECRET_KEY")
                    if sk is not None:
                        prov_cfg.secret_key = sk
                if name == "minimax":
                    gid = os.environ.get("MINIMAX_GROUP_ID")
                    if gid is not None:
                        prov_cfg.group_id = gid

        # 服务器配置
        if os.environ.get("SERVER_PORT"):
            try:
                config.server.port = int(os.environ["SERVER_PORT"])
            except ValueError:
                pass
        if os.environ.get("SERVER_HOST"):
            config.server.host = os.environ["SERVER_HOST"]
        if os.environ.get("DEBUG"):
            config.server.debug = os.environ["DEBUG"].lower() in ("1", "true", "yes")

    def save(self, config: AppConfig):
        """保存配置到文件"""
        try:
            self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
                yaml.dump(config.model_dump(), f, default_flow_style=False, allow_unicode=True)
            self._config = config
            print(f"[Config] 配置已保存到: {self.CONFIG_FILE}")
        except Exception as e:
            print(f"[Config] 保存配置失败: {e}")
            raise

    def _create_default(self) -> AppConfig:
        """创建默认配置"""
        config = AppConfig()

        # 初始化所有提供商配置（空API Key）
        config.qwen = QwenConfig(
            api_key="",
            model="qwen-plus",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )

        config.glm = GLMConfig(
            api_key="",
            model="glm-4-flash",
            base_url="https://open.bigmodel.cn/api/paas/v4/"
        )

        config.deepseek = DeepSeekConfig(
            api_key="",
            model="deepseek-chat",
            base_url="https://api.deepseek.com/v1"
        )

        config.moonshot = MoonshotConfig(
            api_key="",
            model="moonshot-v1-8k",
            base_url="https://api.moonshot.cn/v1"
        )

        config.baidu = BaiduConfig(
            api_key="",
            secret_key="",
            model="ernie-bot-4",
            base_url="https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop"
        )

        config.doubao = DoubaoConfig(
            api_key="",
            model="doubao-pro-4k",
            base_url="https://ark.cn-beijing.volces.com/api/v3"
        )

        config.minimax = MiniMaxConfig(
            api_key="",
            group_id="",
            model="abab6.5-chat",
            base_url="https://api.minimax.chat/v1"
        )

        # 服务器配置
        config.server = ServerConfig(
            port=8765,
            host="0.0.0.0",
            debug=False,
            temp_dir="/tmp/course-doc-generator"
        )

        return config

    def get_llm_config(self) -> dict:
        """获取当前LLM配置"""
        config = self.load()
        provider = config.llm_provider

        provider_config_map = {
            "qwen": config.qwen,
            "glm": config.glm,
            "deepseek": config.deepseek,
            "moonshot": config.moonshot,
            "baidu": config.baidu,
            "doubao": config.doubao,
            "minimax": config.minimax,
        }

        provider_config = provider_config_map.get(provider)
        if provider_config:
            return {
                "provider": provider,
                **provider_config.model_dump()
            }
        else:
            raise ValueError(f"未找到 {provider} 的配置")

    def get_provider_config(self, provider: str) -> dict:
        """获取指定提供商的LLM配置

        Args:
            provider: 提供商名称 (qwen/glm/deepseek/moonshot/baidu/doubao/minimax)

        Returns:
            包含provider、api_key、model、base_url等的配置字典

        Raises:
            ValueError: 如果提供商不支持
        """
        config = self.load()

        provider_config_map = {
            "qwen": config.qwen,
            "glm": config.glm,
            "deepseek": config.deepseek,
            "moonshot": config.moonshot,
            "baidu": config.baidu,
            "doubao": config.doubao,
            "minimax": config.minimax,
        }

        provider_config = provider_config_map.get(provider)
        if provider_config:
            return {
                "provider": provider,
                **provider_config.model_dump()
            }
        else:
            raise ValueError(f"未找到 {provider} 的配置")

    def set_llm_config(self, provider: str, api_key: str, model: str, **kwargs):
        """设置LLM配置"""
        config = self.load()
        config.llm_provider = provider

        if provider == "qwen":
            config.qwen = QwenConfig(
                api_key=api_key,
                model=model,
                base_url=kwargs.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
            )
        elif provider == "glm":
            config.glm = GLMConfig(
                api_key=api_key,
                model=model,
                base_url=kwargs.get("base_url", "https://open.bigmodel.cn/api/paas/v4/")
            )
        elif provider == "deepseek":
            config.deepseek = DeepSeekConfig(
                api_key=api_key,
                model=model,
                base_url=kwargs.get("base_url", "https://api.deepseek.com/v1")
            )
        elif provider == "moonshot":
            config.moonshot = MoonshotConfig(
                api_key=api_key,
                model=model,
                base_url=kwargs.get("base_url", "https://api.moonshot.cn/v1")
            )
        elif provider == "baidu":
            config.baidu = BaiduConfig(
                api_key=api_key,
                secret_key=kwargs.get("secret_key", ""),
                model=model,
                base_url=kwargs.get("base_url", "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop")
            )
        elif provider == "doubao":
            config.doubao = DoubaoConfig(
                api_key=api_key,
                model=model,
                base_url=kwargs.get("base_url", "https://ark.cn-beijing.volces.com/api/v3")
            )
        elif provider == "minimax":
            config.minimax = MiniMaxConfig(
                api_key=api_key,
                group_id=kwargs.get("group_id", ""),
                model=model,
                base_url=kwargs.get("base_url", "https://api.minimax.chat/v1")
            )

        self.save(config)

    def set_processing_config(self, extract_images: bool = None, image_quality: str = None,
                               output_format: str = None, language: str = None):
        """保存处理选项配置"""
        config = self.load()

        if extract_images is not None:
            config.processing.extract_images = extract_images
        if image_quality is not None:
            config.processing.image_quality = image_quality
        if output_format is not None:
            config.processing.output_format = output_format
        if language is not None:
            config.processing.language = language

        self.save(config)

    def set_advanced_config(self, chunk_size: int = None, temperature: float = None,
                           max_retries: int = None):
        """保存高级选项配置"""
        config = self.load()

        if chunk_size is not None:
            config.advanced.chunk_size = chunk_size
        if temperature is not None:
            config.advanced.temperature = temperature
        if max_retries is not None:
            config.advanced.max_retries = max_retries

        self.save(config)

    def set_pdf_watermarks_config(self, enabled: bool = None, patterns: list = None):
        """保存PDF水印过滤配置"""
        config = self.load()

        if enabled is not None:
            config.pdf_watermarks.enabled = enabled
        if patterns is not None:
            config.pdf_watermarks.patterns = patterns

        self.save(config)

    def get_full_config(self) -> dict:
        """获取完整配置（用于前端显示）"""
        config = self.load()
        return {
            "llm_provider": config.llm_provider,
            "qwen": config.qwen.model_dump() if config.qwen else None,
            "glm": config.glm.model_dump() if config.glm else None,
            "deepseek": config.deepseek.model_dump() if config.deepseek else None,
            "moonshot": config.moonshot.model_dump() if config.moonshot else None,
            "baidu": config.baidu.model_dump() if config.baidu else None,
            "doubao": config.doubao.model_dump() if config.doubao else None,
            "minimax": config.minimax.model_dump() if config.minimax else None,
            "processing": config.processing.model_dump(),
            "advanced": config.advanced.model_dump(),
            "pdf_watermarks": config.pdf_watermarks.model_dump(),
            "default_models": config.default_models
        }

    def verify_api_key(self, provider: str, api_key: str) -> dict:
        """验证API Key是否有效"""
        # 这里可以实现实际的API验证逻辑
        # 暂时返回模拟结果
        return {
            "valid": True,
            "message": "API Key 格式正确"
        }


# 全局配置管理器实例
config_manager = ConfigManager()
