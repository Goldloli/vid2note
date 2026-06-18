"""配置 API 集成测试"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from vid2note_core.storage.db import Database
from vid2note_server.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_db(tmp_path, monkeypatch):
    Database.reset_instance()
    # 把 ConfigManager 的默认路径指向临时目录，避免污染真实 config/config.yaml
    tmp_config = tmp_path / "config.yaml"
    monkeypatch.setattr(
        "vid2note_core.config.manager.ConfigManager.__init__",
        lambda self, config_path=None: _init(self, tmp_config),
    )
    yield
    Database.reset_instance()


def _init(self, config_path):
    """替代 ConfigManager.__init__，固定 config_path 到临时文件。"""
    from vid2note_core.config.keychain import KeychainStore

    self.config_path = Path(config_path)
    self.keychain = KeychainStore()
    self._config = None


def test_update_retention_fields():
    """PUT /config 应持久化保留策略字段（不再被静默丢弃）。"""
    resp = client.put(
        "/api/v1/config",
        json={
            "keep_video": True,
            "keep_audio": False,
            "keep_srt": True,
            "keep_markdown": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    changed = data["changed"]
    assert "retention.keep_video" in changed
    assert "retention.keep_audio" in changed
    assert "retention.keep_srt" in changed
    assert "retention.keep_markdown" in changed


def test_update_language_and_mindmap_format():
    """处理选项字段应被持久化。"""
    resp = client.put(
        "/api/v1/config",
        json={"language": "en", "mindmap_format": "outline"},
    )
    assert resp.status_code == 200
    changed = resp.json()["changed"]
    assert "processing.language" in changed
    assert "processing.mindmap_format" in changed


def test_update_providers():
    """provider 字段应被持久化。"""
    resp = client.put(
        "/api/v1/config",
        json={"llm_provider": "glm", "asr_provider": "funasr"},
    )
    assert resp.status_code == 200
    changed = resp.json()["changed"]
    assert "llm_provider" in changed
    assert "asr.provider" in changed


def test_get_config_masks_api_keys():
    """GET /config 不应返回明文密钥。"""
    resp = client.get("/api/v1/config")
    assert resp.status_code == 200

    # 遍历返回值，确认没有明文 api_key
    def _has_plaintext_key(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if "api_key" in k and isinstance(v, str) and v not in ("", "***"):
                    return True
                if _has_plaintext_key(v):
                    return True
        elif isinstance(obj, list):
            return any(_has_plaintext_key(x) for x in obj)
        return False

    assert not _has_plaintext_key(resp.json())
