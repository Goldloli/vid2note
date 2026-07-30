"""
LLM 工厂类
用于创建不同的 LLM 实例
"""
from typing import Dict, Any

from .base import BaseLLM
from .qwen import QwenLLM
from .glm import GLMLLM
from .deepseek import DeepSeekLLM
from .moonshot import MoonshotLLM
from .baidu import BaiduLLM
from .doubao import DoubaoLLM
from .minimax import MiniMaxLLM
from .mock import MockLLM
from .ollama import OllamaLLM
from .custom import CustomLLM


class LLMFactory:
    """LLM 工厂类"""

    _providers = {
        "qwen": QwenLLM,
        "glm": GLMLLM,
        "deepseek": DeepSeekLLM,
        "moonshot": MoonshotLLM,
        "baidu": BaiduLLM,
        "doubao": DoubaoLLM,
        "minimax": MiniMaxLLM,
        "ollama": OllamaLLM,
        "custom": CustomLLM,
        "mock": MockLLM,
    }
    
    @classmethod
    def create(cls, provider: str, config: Dict[str, Any]) -> BaseLLM:
        """
        创建 LLM 实例
        
        Args:
            provider: 提供商名称 (qwen/glm)
            config: 配置字典，包含 api_key, model 等
            
        Returns:
            BaseLLM 实例
            
        Raises:
            ValueError: 如果提供商不支持
        """
        provider = provider.lower()
        
        if provider not in cls._providers:
            raise ValueError(f"不支持的LLM提供商: {provider}。支持的提供商: {list(cls._providers.keys())}")
        
        llm_class = cls._providers[provider]
        return llm_class(**config)
    
    @classmethod
    def get_available_providers(cls) -> list:
        """获取支持的提供商列表"""
        return list(cls._providers.keys())
    
    @classmethod
    def register_provider(cls, name: str, llm_class: type):
        """
        注册新的 LLM 提供商
        
        Args:
            name: 提供商名称
            llm_class: LLM 类，必须继承自 BaseLLM
        """
        if not issubclass(llm_class, BaseLLM):
            raise ValueError("LLM类必须继承自BaseLLM")
        cls._providers[name.lower()] = llm_class
