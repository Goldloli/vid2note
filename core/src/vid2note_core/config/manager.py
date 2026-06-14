"""配置管理器"""
import json
import os
from pathlib import Path
from typing import Optional
from vid2note_core.config.models import AppConfig
from vid2note_core.config.keychain import KeychainStore


class ConfigManager:
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path("config/config.yaml")
        self.keychain = KeychainStore()
        self._config: Optional[AppConfig] = None

    def load(self) -> AppConfig:
        if self._config is not None:
            return self._config
        if self.config_path.exists():
            import yaml
            data = yaml.safe_load(self.config_path.read_text())
            self._config = AppConfig(**data)
        else:
            self._config = AppConfig()
        return self._config

    def save(self, config: AppConfig) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        import yaml
        self.config_path.write_text(yaml.safe_dump(config.model_dump(), allow_unicode=True))
        self._config = config

    def get_api_key(self, provider: str) -> Optional[str]:
        # 1. 尝试 keychain
        key = self.keychain.get(f"{provider}_api_key")
        if key:
            return key
        # 2. 尝试环境变量
        return os.environ.get(f"{provider.upper()}_API_KEY")

    def set_api_key(self, provider: str, api_key: str) -> None:
        self.keychain.set(f"{provider}_api_key", api_key)
