"""文件化设置与加密凭证存储。

公开设置保存在 ``${DATA_ROOT}/config/settings.json``；敏感值使用 Fernet
认证加密后保存在同目录的 ``credentials.enc``。两类文件均通过同目录临时
文件 + ``os.replace`` 原子替换，避免容器中断时留下半写文件。
"""
from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Mapping

from cryptography.fernet import Fernet, InvalidToken


SCHEMA_VERSION = 1
SENSITIVE_LEGACY_KEYS = frozenset(
    {"llm.credentials", "asr.config", "bilibili.cookie"}
)
PUBLIC_LLM_PROFILE_FIELDS = frozenset(
    {"display_name", "model", "base_url", "timeout"}
)


class SettingsFileError(RuntimeError):
    """设置文件格式错误或无法安全落盘。"""


class CredentialConfigurationError(RuntimeError):
    """主密钥缺失、格式错误或权限不安全。"""


class CredentialIntegrityError(RuntimeError):
    """凭证密文被篡改、损坏或使用了错误的主密钥。"""


def _default_data_root() -> Path:
    configured = (os.environ.get("DATA_ROOT") or "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[3] / "data"


def _atomic_write(path: Path, payload: bytes, mode: int) -> None:
    """在目标目录内写临时文件并原子替换。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        os.chmod(path, mode)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            # 某些文件系统不支持目录 fsync；文件本身已成功原子替换。
            pass
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        temp_path.unlink(missing_ok=True)
        raise


def _json_payload(value: Any, *, label: str) -> bytes:
    try:
        return (
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SettingsFileError(f"{label} 包含无法序列化的值") from exc


class SettingsStore:
    """版本化、原子写入的公开设置文件。"""

    def __init__(self, data_root: str | Path | None = None) -> None:
        self.data_root = Path(data_root) if data_root is not None else _default_data_root()
        self.config_dir = self.data_root / "config"
        self.path = self.config_dir / "settings.json"
        self.backup_path = self.config_dir / "settings.json.last-good"

    def exists(self) -> bool:
        return self.path.is_file()

    def read(self) -> dict[str, Any]:
        return self._read_path(self.path)

    def read_last_good(self) -> dict[str, Any]:
        return self._read_path(self.backup_path)

    @staticmethod
    def _read_path(path: Path) -> dict[str, Any]:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SettingsFileError(f"无法读取设置文件：{path}") from exc

        if not isinstance(document, dict):
            raise SettingsFileError("设置文件根节点必须是对象")
        if document.get("schema_version") != SCHEMA_VERSION:
            raise SettingsFileError("设置文件版本不受支持")
        settings = document.get("settings")
        if not isinstance(settings, dict) or not all(
            isinstance(key, str) for key in settings
        ):
            raise SettingsFileError("settings 必须是字符串键对象")
        return dict(settings)

    def write(self, settings: Mapping[str, Any]) -> None:
        if not isinstance(settings, Mapping) or not all(
            isinstance(key, str) for key in settings
        ):
            raise SettingsFileError("settings 必须是字符串键对象")
        document = {
            "schema_version": SCHEMA_VERSION,
            "settings": dict(settings),
        }
        payload = _json_payload(document, label="设置")
        try:
            _atomic_write(self.path, payload, 0o600)
            # 保留最后一次成功解析、成功写入的副本，供人工恢复。
            _atomic_write(self.backup_path, payload, 0o600)
        except OSError as exc:
            raise SettingsFileError(f"无法写入设置文件：{self.path}") from exc


class CredentialStore:
    """Fernet 认证加密的敏感凭证仓库。"""

    def __init__(self, data_root: str | Path | None = None) -> None:
        self.data_root = Path(data_root) if data_root is not None else _default_data_root()
        self.config_dir = self.data_root / "config"
        self.path = self.config_dir / "credentials.enc"
        default_key_path = self.config_dir / "master.key"
        configured_key_path = (
            os.environ.get("VID2NOTE_MASTER_KEY_FILE") or str(default_key_path)
        ).strip()
        self.key_path = Path(configured_key_path).expanduser()
        self._master_key, self.master_key_source = self._resolve_master_key()
        try:
            self._fernet = Fernet(self._master_key)
        except (TypeError, ValueError) as exc:
            raise CredentialConfigurationError("VID2NOTE 主密钥不是合法 Fernet 密钥") from exc

    @staticmethod
    def generate_key() -> bytes:
        return Fernet.generate_key()

    @property
    def master_key(self) -> bytes:
        return self._master_key

    def _resolve_master_key(self) -> tuple[bytes, str]:
        env_key = (os.environ.get("VID2NOTE_MASTER_KEY") or "").strip()
        if env_key:
            return env_key.encode("ascii"), "environment"

        configured_file = (os.environ.get("VID2NOTE_MASTER_KEY_FILE") or "").strip()
        docker_secret_path = Path("/run/secrets/vid2note_master_key")
        if configured_file or docker_secret_path.is_file():
            key_path = (
                Path(configured_file).expanduser()
                if configured_file
                else docker_secret_path
            )
            try:
                return key_path.read_bytes().strip(), "file"
            except OSError as exc:
                raise CredentialConfigurationError(
                    f"无法读取 VID2NOTE_MASTER_KEY_FILE：{key_path}"
                ) from exc

        if self.key_path.exists():
            try:
                key = self.key_path.read_bytes().strip()
            except OSError as exc:
                raise CredentialConfigurationError(
                    f"无法读取本地主密钥：{self.key_path}"
                ) from exc
            self._ensure_private_mode(self.key_path)
            return key, "generated"

        key = self.generate_key()
        try:
            _atomic_write(self.key_path, key + b"\n", 0o600)
        except OSError as exc:
            raise CredentialConfigurationError(
                f"无法生成本地主密钥：{self.key_path}"
            ) from exc
        return key, "generated"

    @staticmethod
    def _ensure_private_mode(path: Path) -> None:
        current_mode = stat.S_IMODE(path.stat().st_mode)
        if current_mode & 0o077:
            os.chmod(path, 0o600)

    def read_all(self) -> dict[str, Any]:
        try:
            ciphertext = self.path.read_bytes()
        except FileNotFoundError:
            return {}
        except OSError as exc:
            raise CredentialIntegrityError(f"无法读取凭证文件：{self.path}") from exc
        try:
            plaintext = self._fernet.decrypt(ciphertext)
            values = json.loads(plaintext.decode("utf-8"))
        except (InvalidToken, UnicodeError, json.JSONDecodeError) as exc:
            raise CredentialIntegrityError("凭证密文校验失败") from exc
        if not isinstance(values, dict):
            raise CredentialIntegrityError("凭证文件根节点必须是对象")
        return values

    def write_all(self, values: Mapping[str, Any]) -> None:
        if not isinstance(values, Mapping):
            raise SettingsFileError("凭证必须是对象")
        plaintext = _json_payload(dict(values), label="凭证")
        ciphertext = self._fernet.encrypt(plaintext)
        try:
            _atomic_write(self.path, ciphertext, 0o600)
        except OSError as exc:
            raise CredentialIntegrityError(f"无法写入凭证文件：{self.path}") from exc

    def get(self, namespace: str, subject: str, field: str, default: Any = None) -> Any:
        values = self.read_all()
        return (
            values.get(namespace, {})
            .get(subject, {})
            .get(field, default)
        )

    def update_fields(
        self, namespace: str, subject: str, fields: Mapping[str, Any]
    ) -> None:
        values = self.read_all()
        target = values.setdefault(namespace, {}).setdefault(subject, {})
        for field, value in fields.items():
            if value is not None:
                target[field] = value
        self.write_all(values)

    def clear_field(self, namespace: str, subject: str, field: str) -> bool:
        values = self.read_all()
        target = values.get(namespace, {}).get(subject, {})
        if field not in target:
            return False
        del target[field]
        if not target:
            values.get(namespace, {}).pop(subject, None)
        if not values.get(namespace):
            values.pop(namespace, None)
        self.write_all(values)
        return True


def _decode_json_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if not raw:
        return {}
    try:
        parsed = json.loads(str(raw))
    except (TypeError, ValueError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def migrate_legacy_settings(
    repo: Any,
    settings_store: SettingsStore,
    credential_store: CredentialStore,
) -> bool:
    """把旧 SQLite settings 一次性搬到文件存储。

    只有两份新文件均可读回且内容一致后才删除 SQLite 中的敏感键。任一步失败
    均返回 ``False`` 并保留旧值，以便继续使用旧配置或稍后重试。
    """
    try:
        legacy = dict(repo.get_all_settings() or {})
    except Exception:
        return False
    if not legacy:
        return False

    try:
        current = settings_store.read() if settings_store.exists() else {}
    except SettingsFileError:
        return False
    if current.get("migration.sqlite_settings_v1") is True:
        return False

    public: dict[str, Any] = dict(current)
    public.update(
        {
            key: value
            for key, value in legacy.items()
            if key not in SENSITIVE_LEGACY_KEYS
        }
    )
    secrets: dict[str, Any] = credential_store.read_all()

    llm_credentials = _decode_json_object(legacy.get("llm.credentials"))
    if llm_credentials:
        llm_target = secrets.setdefault("llm", {})
        profile_target = public.setdefault("llm.providers", {})
        if not isinstance(profile_target, dict):
            profile_target = {}
            public["llm.providers"] = profile_target

        def split_provider_fields(provider: str, fields: dict[str, Any]) -> None:
            public_fields = {
                key: value
                for key, value in fields.items()
                if key in PUBLIC_LLM_PROFILE_FIELDS
            }
            secret_fields = {
                key: value
                for key, value in fields.items()
                if key not in PUBLIC_LLM_PROFILE_FIELDS
            }
            if public_fields:
                profile_target.setdefault(provider, {}).update(public_fields)
            if secret_fields:
                llm_target.setdefault(provider, {}).update(secret_fields)

        if any(isinstance(value, dict) for value in llm_credentials.values()):
            for provider, fields in llm_credentials.items():
                if isinstance(fields, dict):
                    split_provider_fields(str(provider), fields)
        else:
            provider = str(legacy.get("llm.provider") or "deepseek")
            split_provider_fields(provider, llm_credentials)

    asr_config = _decode_json_object(legacy.get("asr.config"))
    external_key = asr_config.pop("external_api_key", None)
    if external_key:
        secrets.setdefault("asr", {}).setdefault("external", {})["api_key"] = external_key
    if asr_config:
        public["asr.config"] = asr_config

    cookie_raw = legacy.get("bilibili.cookie")
    if cookie_raw:
        cookie_object = _decode_json_object(cookie_raw)
        cookie = cookie_object.get("cookie") if cookie_object else str(cookie_raw)
        if cookie:
            secrets.setdefault("media", {}).setdefault("bilibili", {})["cookie"] = cookie

    public["migration.sqlite_settings_v1"] = True
    try:
        credential_store.write_all(secrets)
        if credential_store.read_all() != secrets:
            raise CredentialIntegrityError("凭证迁移回读校验失败")
        settings_store.write(public)
        if settings_store.read() != public:
            raise SettingsFileError("设置迁移回读校验失败")
    except Exception:
        return False

    try:
        for key in SENSITIVE_LEGACY_KEYS:
            if key in legacy:
                repo.delete_setting(key)
    except Exception:
        # 数据已经安全迁移；删除失败只会留下旧副本，下次启动可再次清理。
        return False
    return True


__all__ = [
    "CredentialConfigurationError",
    "CredentialIntegrityError",
    "CredentialStore",
    "SettingsFileError",
    "SettingsStore",
    "migrate_legacy_settings",
]
