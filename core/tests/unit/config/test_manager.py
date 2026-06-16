"""测试配置管理器"""

from pathlib import Path
from vid2note_core.config.manager import ConfigManager
from vid2note_core.config.models import AppConfig


def test_load_default_config():
    mgr = ConfigManager(config_path=Path("/tmp/nonexistent.yaml"))
    config = mgr.load()
    assert config.llm_provider == "qwen"
    assert config.asr.provider == "asrtools-b"


def test_save_and_load_config(tmp_path):
    path = tmp_path / "config.yaml"
    mgr = ConfigManager(config_path=path)
    config = AppConfig(llm_provider="glm")
    mgr.save(config)
    assert path.exists()

    mgr2 = ConfigManager(config_path=path)
    loaded = mgr2.load()
    assert loaded.llm_provider == "glm"
