"""运行时设置快照、文件权威态与凭证解析。"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

from src.core.kernel import logger
from src.llm.provider_registry import PROVIDER_REGISTRY, provider_profiles
from src.runtime.settings_store import (
    CredentialStore,
    SettingsFileError,
    SettingsStore,
    migrate_legacy_settings,
)


SUPPORTED_LLM_PROVIDERS = frozenset(PROVIDER_REGISTRY)
DEFAULT_LLM_MODELS: Dict[str, str] = {
    key: item.default_model for key, item in PROVIDER_REGISTRY.items()
}
DEFAULT_LLM_BASE_URLS: Dict[str, str] = {
    key: item.default_base_url for key, item in PROVIDER_REGISTRY.items()
}

DEFAULT_SETTINGS: Dict[str, str] = {
    "llm.provider": "deepseek",
    "llm.model": "deepseek-v4-flash",
    "llm.providers": "{}",
    # 兼容旧调用；新文件永不持久化该键。
    "llm.credentials": "{}",
    "asr.engine": "bcut",
    "asr.strategy": "online_first",
    "asr.config": "{}",
    "pdf.mode": "pypdf",
    # 兼容旧调用；新文件永不持久化该键。
    "bilibili.cookie": "{}",
    "concurrency.max": "1",
    "note.output_language": "zh",
    "note.detail_level": "balanced",
    "note.extract_images": "false",
    "note.image_quality": "medium",
    "ui.language": "zh",
    "ui.theme": "system",
    "ui.background": "plain",
    "retention.video": "7d",
    "retention.audio": "7d",
    "retention.srt": "30d",
    "retention.note": "permanent",
    "retention.screenshot": "30d",
    "advanced.chunk_size": "4000",
    "advanced.temperature": "0.3",
    "advanced.max_retries": "3",
}

MIN_CONCURRENCY = 1
MAX_CONCURRENCY = 3
DEFAULT_CONCURRENCY = 1
_RETENTION_VALUES = frozenset({"permanent", "7d", "30d"})
_LANGUAGES = frozenset({"zh", "en"})
_DETAIL_LEVELS = frozenset({"concise", "balanced", "detailed", "exhaustive"})
_PDF_MODES = frozenset({"pypdf"})
_ASR_ENGINES = frozenset({"bcut", "whisper_cpp", "external"})


def clamp_concurrency(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return DEFAULT_CONCURRENCY
    return min(MAX_CONCURRENCY, max(MIN_CONCURRENCY, n))


def _coerce_enum(value: Any, allowed: frozenset[str], default: str) -> str:
    normalized = str(value).strip().lower() if value is not None else ""
    return normalized if normalized in allowed else default


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower() if value is not None else ""
    return normalized in ("1", "true", "yes", "on")


def _snapshot_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _legacy_settings(repo: Any) -> dict[str, Any]:
    if repo is None:
        return {}
    try:
        return dict(repo.get_all_settings() or {})
    except Exception:
        logger.debug("读取 SQLite settings 失败", exc_info=True)
        return {}


def _read_authoritative_settings(repo: Any) -> dict[str, Any]:
    store = SettingsStore()
    files_enabled = bool(os.environ.get("DATA_ROOT")) or store.exists()
    if not files_enabled:
        return _legacy_settings(repo)

    if not store.exists() and repo is not None:
        legacy = _legacy_settings(repo)
        if legacy:
            try:
                migrated = migrate_legacy_settings(repo, store, CredentialStore())
            except Exception:
                migrated = False
                logger.exception("旧设置迁移失败，暂时回落 SQLite")
            if not migrated:
                return legacy
        else:
            public_defaults = {
                key: value
                for key, value in DEFAULT_SETTINGS.items()
                if key not in {"llm.credentials", "bilibili.cookie"}
            }
            store.write(public_defaults)

    try:
        return store.read()
    except SettingsFileError:
        logger.exception("settings.json 损坏，尝试最后一次有效副本")
        try:
            backup = store.read_last_good()
        except SettingsFileError:
            backup = {}
        return backup or _legacy_settings(repo)


def get_settings_snapshot(repo: Any = None) -> Dict[str, str]:
    """读取文件权威态并补齐合法默认值；迁移失败时回落旧 SQLite。"""
    raw = _read_authoritative_settings(repo)
    snapshot: Dict[str, str] = dict(DEFAULT_SETTINGS)
    for key, value in raw.items():
        if value is not None:
            snapshot[key] = _snapshot_value(value)

    if "llm.provider" not in raw:
        env_provider = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
        if env_provider in SUPPORTED_LLM_PROVIDERS:
            snapshot["llm.provider"] = env_provider
    provider = (snapshot.get("llm.provider") or "deepseek").strip().lower()
    snapshot["llm.provider"] = (
        provider if provider in SUPPORTED_LLM_PROVIDERS else "deepseek"
    )

    profile_overrides = parse_json_object(snapshot.get("llm.providers"))
    profiles = provider_profiles(profile_overrides)
    selected_profile = profiles[snapshot["llm.provider"]]
    if "llm.model" not in raw:
        prefix = snapshot["llm.provider"].upper()
        snapshot["llm.model"] = (
            os.environ.get(f"{prefix}_MODEL")
            or selected_profile["model"]
        )
    snapshot["llm.model"] = str(
        snapshot.get("llm.model") or selected_profile["model"]
    ).strip()
    snapshot["llm.providers"] = json.dumps(profiles, ensure_ascii=False)

    snapshot["asr.engine"] = _coerce_enum(
        snapshot.get("asr.engine"), _ASR_ENGINES, "bcut"
    )
    snapshot["asr.strategy"] = _coerce_enum(
        snapshot.get("asr.strategy"),
        frozenset({"online_first", "single"}),
        "online_first",
    )
    snapshot["pdf.mode"] = _coerce_enum(
        snapshot.get("pdf.mode"), _PDF_MODES, "pypdf"
    )
    snapshot["note.output_language"] = _coerce_enum(
        snapshot.get("note.output_language"), _LANGUAGES, "zh"
    )
    snapshot["note.detail_level"] = _coerce_enum(
        snapshot.get("note.detail_level"), _DETAIL_LEVELS, "balanced"
    )
    snapshot["note.extract_images"] = (
        "true" if _as_bool(snapshot.get("note.extract_images")) else "false"
    )
    for key in (
        "retention.video",
        "retention.audio",
        "retention.srt",
        "retention.note",
        "retention.screenshot",
    ):
        snapshot[key] = _coerce_enum(
            snapshot.get(key), _RETENTION_VALUES, DEFAULT_SETTINGS[key]
        )
    return snapshot


def parse_json_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def get_credentials(snapshot: Dict[str, str], provider: str) -> Dict[str, Any]:
    """解析指定 provider 凭证，优先加密文件，其次旧快照和环境变量。"""
    normalized = str(provider or "").strip().lower()
    resolved: dict[str, Any] = {}
    credential_store = CredentialStore()
    if credential_store.path.exists():
        try:
            resolved.update(
                credential_store.read_all().get("llm", {}).get(normalized, {})
            )
        except Exception:
            logger.exception("读取加密 LLM 凭证失败")

    legacy = parse_json_object(snapshot.get("llm.credentials"))
    if normalized in legacy and isinstance(legacy[normalized], dict):
        for key, value in legacy[normalized].items():
            resolved.setdefault(key, value)
    elif not any(isinstance(value, dict) for value in legacy.values()):
        for key, value in legacy.items():
            resolved.setdefault(key, value)

    profile_overrides = parse_json_object(snapshot.get("llm.providers"))
    profiles = provider_profiles(profile_overrides)
    if normalized in profiles:
        explicit_profile = profile_overrides.get(normalized)
        explicit_profile = (
            explicit_profile if isinstance(explicit_profile, dict) else {}
        )
        for field in ("base_url", "model", "timeout", "display_name"):
            value = explicit_profile.get(field)
            if value not in (None, ""):
                resolved.setdefault(field, value)

    prefix = normalized.upper()
    for field, value in {
        "api_key": os.environ.get(f"{prefix}_API_KEY"),
        "base_url": os.environ.get(f"{prefix}_BASE_URL"),
    }.items():
        is_registry_default = (
            field == "base_url"
            and normalized in DEFAULT_LLM_BASE_URLS
            and resolved.get(field) == DEFAULT_LLM_BASE_URLS[normalized]
        )
        if value and (not resolved.get(field) or is_registry_default):
            resolved[field] = value
    if normalized in profiles:
        for field in ("base_url", "model", "timeout", "display_name"):
            value = profiles[normalized].get(field)
            if value not in (None, ""):
                resolved.setdefault(field, value)
    if normalized in DEFAULT_LLM_BASE_URLS and not resolved.get("base_url"):
        resolved["base_url"] = DEFAULT_LLM_BASE_URLS[normalized]
    if normalized == "ollama" and not resolved.get("api_key"):
        resolved["api_key"] = "ollama"
    return resolved


def get_external_asr_api_key() -> str:
    """读取加密的外部 ASR API Key，并兼容环境变量部署。"""
    store = CredentialStore()
    if store.path.exists():
        try:
            value = store.get("asr", "external", "api_key")
            if value:
                return str(value)
        except Exception:
            logger.exception("读取加密外部 ASR 凭证失败")
    return os.environ.get("EXTERNAL_ASR_API_KEY", "")


def get_bilibili_cookies(snapshot: Dict[str, str] | None = None) -> dict[str, str]:
    """读取并解析加密的 Bilibili Cookie，仅返回下载器需要的三个字段。"""
    raw: Any = ""
    store = CredentialStore()
    if store.path.exists():
        try:
            raw = store.get("media", "bilibili", "cookie", "")
        except Exception:
            logger.exception("读取加密 Bilibili Cookie 失败")
    if not raw:
        raw = os.environ.get("BILIBILI_COOKIE", "")
    if not raw and snapshot:
        # 仅用于迁移失败时的旧 SQLite 回落；新设置文件不会保存该键。
        raw = snapshot.get("bilibili.cookie", "")

    parsed: dict[str, Any] = {}
    if isinstance(raw, dict):
        parsed = dict(raw)
    elif raw:
        text = str(raw).strip()
        parsed = parse_json_object(text)
        if not parsed:
            for item in text.split(";"):
                name, separator, value = item.strip().partition("=")
                if separator and name:
                    parsed[name] = value

    allowed = ("SESSDATA", "bili_jct", "DedeUserID")
    return {
        key: str(parsed[key]).strip()
        for key in allowed
        if str(parsed.get(key, "")).strip()
    }


def default_model_for(provider: str) -> str:
    normalized = str(provider or "").strip().lower()
    if normalized not in SUPPORTED_LLM_PROVIDERS:
        raise ValueError(f"不支持的 LLM 提供商：{provider}")
    return DEFAULT_LLM_MODELS[normalized]


__all__ = [
    "DEFAULT_CONCURRENCY",
    "DEFAULT_LLM_BASE_URLS",
    "DEFAULT_LLM_MODELS",
    "DEFAULT_SETTINGS",
    "MAX_CONCURRENCY",
    "MIN_CONCURRENCY",
    "SUPPORTED_LLM_PROVIDERS",
    "clamp_concurrency",
    "default_model_for",
    "get_bilibili_cookies",
    "get_credentials",
    "get_external_asr_api_key",
    "get_settings_snapshot",
    "parse_json_object",
]
