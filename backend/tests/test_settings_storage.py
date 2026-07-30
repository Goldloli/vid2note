"""独立设置文件与加密凭证存储的契约测试。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.runtime.settings_store import (
    CredentialIntegrityError,
    CredentialStore,
    SettingsFileError,
    SettingsStore,
    migrate_legacy_settings,
)


class LegacyRepo:
    """最小旧版 SQLite settings 仓库替身。"""

    def __init__(self, values: dict[str, str]) -> None:
        self.values = dict(values)
        self.deleted: list[str] = []

    def get_all_settings(self) -> dict[str, str]:
        return dict(self.values)

    def delete_setting(self, key: str) -> None:
        self.deleted.append(key)
        self.values.pop(key, None)


class TestSettingsStore:
    def test_round_trip_uses_versioned_document_and_atomic_replace(self, tmp_path):
        store = SettingsStore(tmp_path)

        store.write(
            {
                "llm.provider": "deepseek",
                "note.detail_level": "balanced",
                "concurrency.max": "2",
            }
        )

        assert store.read() == {
            "llm.provider": "deepseek",
            "note.detail_level": "balanced",
            "concurrency.max": "2",
        }
        document = json.loads(store.path.read_text(encoding="utf-8"))
        assert document["schema_version"] == 1
        assert document["settings"]["note.detail_level"] == "balanced"
        assert list(store.config_dir.glob("*.tmp")) == []

    def test_rejects_invalid_root_or_unsupported_value(self, tmp_path):
        store = SettingsStore(tmp_path)
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text("[]", encoding="utf-8")

        with pytest.raises(SettingsFileError):
            store.read()
        with pytest.raises(SettingsFileError):
            store.write({"bad": {"not", "json"}})

    def test_corrupt_file_does_not_destroy_last_known_good_copy(self, tmp_path):
        store = SettingsStore(tmp_path)
        store.write({"llm.provider": "deepseek"})
        store.path.write_text("{broken", encoding="utf-8")

        with pytest.raises(SettingsFileError):
            store.read()
        assert store.backup_path.exists()
        assert json.loads(store.backup_path.read_text(encoding="utf-8"))["settings"] == {
            "llm.provider": "deepseek"
        }


class TestCredentialStore:
    def test_master_key_precedence_env_then_explicit_file_then_generated(
        self, tmp_path, monkeypatch
    ):
        env_key = CredentialStore.generate_key()
        file_key = CredentialStore.generate_key()
        key_file = tmp_path / "docker-secret"
        key_file.write_bytes(file_key + b"\n")
        monkeypatch.setenv("VID2NOTE_MASTER_KEY", env_key.decode())
        monkeypatch.setenv("VID2NOTE_MASTER_KEY_FILE", str(key_file))

        from_env = CredentialStore(tmp_path)
        assert from_env.master_key_source == "environment"
        assert from_env.master_key == env_key

        monkeypatch.delenv("VID2NOTE_MASTER_KEY")
        from_file = CredentialStore(tmp_path)
        assert from_file.master_key_source == "file"
        assert from_file.master_key == file_key

        monkeypatch.delenv("VID2NOTE_MASTER_KEY_FILE")
        generated = CredentialStore(tmp_path)
        assert generated.master_key_source == "generated"
        assert generated.key_path.exists()
        assert os.stat(generated.key_path).st_mode & 0o777 == 0o600

    def test_encrypts_round_trip_and_never_writes_plaintext(self, tmp_path, monkeypatch):
        monkeypatch.delenv("VID2NOTE_MASTER_KEY", raising=False)
        monkeypatch.delenv("VID2NOTE_MASTER_KEY_FILE", raising=False)
        store = CredentialStore(tmp_path)
        values = {
            "llm": {"deepseek": {"api_key": "sk-super-secret"}},
            "asr": {"external": {"api_key": "asr-secret"}},
        }

        store.write_all(values)

        assert store.read_all() == values
        raw = store.path.read_bytes()
        assert b"sk-super-secret" not in raw
        assert b"asr-secret" not in raw
        assert os.stat(store.path).st_mode & 0o777 == 0o600

    def test_tampered_ciphertext_is_rejected(self, tmp_path, monkeypatch):
        monkeypatch.delenv("VID2NOTE_MASTER_KEY", raising=False)
        monkeypatch.delenv("VID2NOTE_MASTER_KEY_FILE", raising=False)
        store = CredentialStore(tmp_path)
        store.write_all({"llm": {"deepseek": {"api_key": "secret"}}})
        ciphertext = bytearray(store.path.read_bytes())
        ciphertext[len(ciphertext) // 2] ^= 1
        store.path.write_bytes(bytes(ciphertext))

        with pytest.raises(CredentialIntegrityError):
            store.read_all()


class TestLegacyMigration:
    def test_migrates_then_removes_sensitive_sqlite_values(self, tmp_path, monkeypatch):
        monkeypatch.delenv("VID2NOTE_MASTER_KEY", raising=False)
        monkeypatch.delenv("VID2NOTE_MASTER_KEY_FILE", raising=False)
        repo = LegacyRepo(
            {
                "llm.provider": "qwen",
                "llm.credentials": json.dumps(
                    {"qwen": {"api_key": "sk-qwen", "base_url": "https://example.test/v1"}}
                ),
                "asr.config": json.dumps(
                    {
                        "external_endpoint": "https://asr.example.test",
                        "external_api_key": "asr-key",
                        "concurrency": 2,
                    }
                ),
                "bilibili.cookie": "SESSDATA=secret",
            }
        )
        settings = SettingsStore(tmp_path)
        credentials = CredentialStore(tmp_path)

        assert migrate_legacy_settings(repo, settings, credentials) is True

        public = settings.read()
        assert public["llm.provider"] == "qwen"
        assert "llm.credentials" not in public
        assert public["llm.providers"]["qwen"]["base_url"] == "https://example.test/v1"
        assert "external_api_key" not in public["asr.config"]
        assert public["asr.config"]["external_endpoint"] == "https://asr.example.test"
        assert public["migration.sqlite_settings_v1"] is True
        secret = credentials.read_all()
        assert secret["llm"]["qwen"] == {"api_key": "sk-qwen"}
        assert secret["asr"]["external"]["api_key"] == "asr-key"
        assert secret["media"]["bilibili"]["cookie"] == "SESSDATA=secret"
        assert set(repo.deleted) == {"llm.credentials", "asr.config", "bilibili.cookie"}

    def test_failed_migration_leaves_sqlite_sensitive_values_intact(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.delenv("VID2NOTE_MASTER_KEY", raising=False)
        monkeypatch.delenv("VID2NOTE_MASTER_KEY_FILE", raising=False)
        repo = LegacyRepo({"llm.credentials": '{"deepseek":{"api_key":"still-safe"}}'})
        settings = SettingsStore(tmp_path)
        credentials = CredentialStore(tmp_path)

        def fail_write(_values):
            raise OSError("disk full")

        monkeypatch.setattr(credentials, "write_all", fail_write)

        assert migrate_legacy_settings(repo, settings, credentials) is False
        assert repo.deleted == []
        assert "llm.credentials" in repo.values
        assert not settings.exists()
