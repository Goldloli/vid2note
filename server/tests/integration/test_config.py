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


def test_get_config_omits_provider_secret_structures():
    payload = client.get("/api/v1/config").json()

    assert "qwen" not in payload
    assert "baidu" not in payload
    assert "minimax" not in payload


def test_update_workspace_defaults():
    response = client.put(
        "/api/v1/config",
        json={
            "vault_path": "/tmp/vid2note-vault",
            "default_runtime": "claude",
            "clip_buffer_ms": 2500,
        },
    )

    assert response.status_code == 200
    assert response.json()["changed"] == [
        "workspace.vault_path",
        "workspace.default_runtime",
        "workspace.clip_buffer_ms",
    ]
    assert client.get("/api/v1/config").json()["workspace"] == {
        "vault_path": "/tmp/vid2note-vault",
        "default_runtime": "claude",
        "clip_buffer_ms": 2500,
    }


def test_store_api_key_uses_keychain(monkeypatch):
    stored = {}
    monkeypatch.setattr(
        "vid2note_core.config.manager.ConfigManager.set_api_key",
        lambda self, provider, api_key: stored.update({provider: api_key}),
    )

    response = client.put(
        "/api/v1/config/api-key",
        json={"provider": "qwen", "api_key": "secret-value"},
    )

    assert response.status_code == 204
    assert stored == {"qwen": "secret-value"}
    assert "secret-value" not in response.text


def test_verify_api_key_does_not_echo_provider_exception(monkeypatch):
    secret = "sk-do-not-echo"

    def fail_with_secret(_provider, config):
        raise RuntimeError(f"provider rejected {config['api_key']}")

    monkeypatch.setattr("vid2note_core.llm.factory.LLMFactory.create", fail_with_secret)

    response = client.post(
        "/api/v1/config/verify",
        json={"provider": "qwen", "api_key": secret},
    )

    assert response.status_code == 200
    assert response.json() == {"valid": False, "error": "API key verification failed"}
    assert secret not in response.text
