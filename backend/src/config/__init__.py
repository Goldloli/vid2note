"""
配置管理模块
"""
from .models import (
    AppConfig, QwenConfig, GLMConfig, DeepSeekConfig,
    MoonshotConfig, BaiduConfig, DoubaoConfig, MiniMaxConfig,
    ProcessingConfig, AdvancedConfig, ServerConfig, PDFWatermarksConfig
)
from .manager import ConfigManager, config_manager

__all__ = [
    "AppConfig",
    "QwenConfig",
    "GLMConfig",
    "DeepSeekConfig",
    "MoonshotConfig",
    "BaiduConfig",
    "DoubaoConfig",
    "MiniMaxConfig",
    "ProcessingConfig",
    "AdvancedConfig",
    "PDFWatermarksConfig",
    "ConfigManager",
    "config_manager",
]
