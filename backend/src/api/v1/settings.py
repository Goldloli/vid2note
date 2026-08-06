"""文件化设置、加密凭证与 LLM 配置 API。"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Response

from src.llm.factory import LLMFactory
from src.llm.provider_registry import (
    PROVIDER_REGISTRY,
    provider_profiles,
    public_provider_registry,
)
from src.runtime.settings import (
    SUPPORTED_LLM_PROVIDERS,
    get_settings_snapshot,
    parse_json_object,
)
from src.runtime.settings_store import CredentialStore, SettingsFileError, SettingsStore
from src.runtime.task_service import get_task_service

router = APIRouter(prefix="/settings", tags=["settings"])

_ENUM_ALLOWED: Dict[str, frozenset[str]] = {
    "asr.engine": frozenset({"bcut", "whisper_cpp", "external"}),
    "asr.strategy": frozenset({"online_first", "single"}),
    "pdf.mode": frozenset({"pypdf"}),
    "note.output_language": frozenset({"zh", "en"}),
    "note.detail_level": frozenset(
        {"concise", "balanced", "detailed", "exhaustive"}
    ),
    "note.image_quality": frozenset({"low", "medium", "high"}),
    "retention.video": frozenset({"permanent", "7d", "30d"}),
    "retention.audio": frozenset({"permanent", "7d", "30d"}),
    "retention.srt": frozenset({"permanent", "7d", "30d"}),
    "retention.note": frozenset({"permanent", "7d", "30d"}),
    "retention.screenshot": frozenset({"permanent", "7d", "30d"}),
    "ui.language": frozenset({"zh", "en"}),
    "ui.theme": frozenset({"system", "light", "dark"}),
    "ui.background": frozenset({"mesh", "static", "plain"}),
}
_NUMERIC_FIELDS = (
    ("concurrency.max", int, 1, 3),
    ("advanced.chunk_size", int, 1, 1_000_000),
    ("advanced.max_retries", int, 0, 20),
)
_FLOAT_FIELDS = (("advanced.temperature", 0.0, 2.0),)
_BOOL_KEYS = frozenset({"note.extract_images"})
_PUBLIC_OBJECT_KEYS = frozenset({"asr.config", "llm.providers"})
_TEXT_KEYS = frozenset({"llm.provider", "llm.model"})
_ASR_CONFIG_FIELDS = frozenset(
    {
        "bcut_timeout",
        "whisper_model_path",
        "whisper_binary",
        "whisper_device",
        "whisper_compute_type",
        "whisper_language",
        "external_endpoint",
        "external_timeout",
        "vad_threshold_seconds",
        # 旧字段仅作为兼容输入，响应与后续保存会迁移到新字段。
        "vad_target_segment_seconds",
        "concurrency",
        "online_target_segment_seconds",
        "local_target_segment_seconds",
        "online_concurrency",
        "local_concurrency",
        "online_audio_format",
        "online_audio_bitrate_kbps",
        "cache_enabled",
        "request_timeout",
    }
)
_ASR_CONFIG_DEFAULTS: dict[str, Any] = {
    "bcut_timeout": 120.0,
    "whisper_model_path": "",
    "whisper_binary": "",
    "whisper_device": "cpu",
    "whisper_compute_type": "int8",
    "whisper_language": "zh",
    "external_endpoint": "",
    "external_timeout": 120.0,
    "vad_threshold_seconds": 300.0,
    "online_target_segment_seconds": 280.0,
    "local_target_segment_seconds": 120.0,
    "online_concurrency": 3,
    "local_concurrency": 1,
    "online_audio_format": "mp3",
    "online_audio_bitrate_kbps": 64,
    "cache_enabled": True,
    "request_timeout": 120.0,
}
_INTERNAL_KEYS = frozenset(
    {
        "llm.credentials",
        "bilibili.cookie",
        "migration.sqlite_settings_v1",
    }
)

_SPECIAL_CREDENTIALS = {
    "external_asr": ("asr", "external", frozenset({"api_key"})),
    "bilibili": ("media", "bilibili", frozenset({"cookie"})),
}


def _validate_scalar(key: str, value: Any) -> str | None:
    known = (
        key in _ENUM_ALLOWED
        or any(item[0] == key for item in _NUMERIC_FIELDS)
        or any(item[0] == key for item in _FLOAT_FIELDS)
        or key in _BOOL_KEYS
        or key in _TEXT_KEYS
    )
    if not known:
        return None

    if key in _BOOL_KEYS:
        normalized = str(value).strip().lower() if value is not None else ""
        if normalized not in ("true", "false", "1", "0", "yes", "no", "on", "off"):
            raise ValueError(f"{key} 必须是布尔值")
        return "true" if normalized in ("true", "1", "yes", "on") else "false"

    for candidate, cast, lower, upper in _NUMERIC_FIELDS:
        if key == candidate:
            try:
                number = cast(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key} 必须是整数") from exc
            if not lower <= number <= upper:
                raise ValueError(f"{key} 取值越界（允许 {lower}~{upper}）")
            return str(number)

    for candidate, lower, upper in _FLOAT_FIELDS:
        if key == candidate:
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key} 必须是数字") from exc
            if not lower <= number <= upper:
                raise ValueError(f"{key} 取值越界（允许 {lower}~{upper}）")
            return str(number)

    if key in _ENUM_ALLOWED:
        normalized = str(value).strip().lower() if value is not None else ""
        allowed = _ENUM_ALLOWED[key]
        if normalized not in allowed:
            raise ValueError(f"{key} 非法取值（允许 {sorted(allowed)}）")
        return normalized

    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"{key} 不能为空")
    if key == "llm.provider":
        text = text.lower()
        if text not in SUPPORTED_LLM_PROVIDERS:
            raise ValueError(
                f"llm.provider 非法取值（允许 {sorted(SUPPORTED_LLM_PROVIDERS)}）"
            )
    return text


def _validate_url(value: Any, label: str) -> str:
    text = str(value or "").strip()
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{label} 必须是 http/https URL")
    return text.rstrip("/")


def _validate_profiles(
    incoming: Any, current: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    if not isinstance(incoming, dict):
        raise ValueError("llm.providers 必须是对象")
    merged = {key: dict(value) for key, value in current.items()}
    for provider, raw in incoming.items():
        if provider not in PROVIDER_REGISTRY:
            raise ValueError(f"未知 LLM provider：{provider}")
        if not isinstance(raw, dict):
            raise ValueError(f"{provider} 配置必须是对象")
        unknown = set(raw) - {"display_name", "model", "base_url", "timeout"}
        if unknown:
            raise ValueError(f"{provider} 包含未知字段：{sorted(unknown)}")
        profile = dict(merged[provider])
        if "display_name" in raw:
            display_name = str(raw["display_name"] or "").strip()
            if not display_name or len(display_name) > 50:
                raise ValueError(f"{provider}.display_name 长度必须为 1~50")
            profile["display_name"] = display_name
        if "model" in raw:
            model = str(raw["model"] or "").strip()
            if not model or len(model) > 200:
                raise ValueError(f"{provider}.model 长度必须为 1~200")
            profile["model"] = model
        if "base_url" in raw:
            profile["base_url"] = _validate_url(
                raw["base_url"], f"{provider}.base_url"
            )
        if "timeout" in raw:
            try:
                timeout = int(raw["timeout"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{provider}.timeout 必须是整数") from exc
            if not 1 <= timeout <= 600:
                raise ValueError(f"{provider}.timeout 允许 1~600 秒")
            profile["timeout"] = timeout
        definition = PROVIDER_REGISTRY[provider]
        if definition.requires_model and not profile.get("model"):
            raise ValueError(f"{provider}.model 不能为空")
        if definition.requires_base_url and not profile.get("base_url"):
            raise ValueError(f"{provider}.base_url 不能为空")
        merged[provider] = profile
    return merged


def _validate_asr_config(incoming: Any, current: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(incoming, dict):
        raise ValueError("asr.config 必须是对象")
    unknown = set(incoming) - _ASR_CONFIG_FIELDS
    if unknown:
        raise ValueError(f"asr.config 包含未知字段：{sorted(unknown)}")
    candidate = _normalize_asr_config(current)
    for key in ("whisper_model_path", "whisper_binary"):
        if key in incoming:
            value = str(incoming[key] or "").strip()
            if len(value) > 4096:
                raise ValueError(f"{key} 长度超出限制")
            if value and not value.startswith("/"):
                raise ValueError(f"{key} 必须是容器内绝对路径")
            candidate[key] = value
    if "whisper_device" in incoming:
        if str(incoming["whisper_device"]).strip().lower() != "cpu":
            raise ValueError("whisper_device 当前仅支持 cpu")
        candidate["whisper_device"] = "cpu"
    if "whisper_compute_type" in incoming:
        if str(incoming["whisper_compute_type"]).strip().lower() != "int8":
            raise ValueError("whisper_compute_type 当前仅支持 int8")
        candidate["whisper_compute_type"] = "int8"
    if "whisper_language" in incoming:
        language = str(incoming["whisper_language"] or "").strip().lower()
        if not language or len(language) > 12 or not language.replace("-", "").isalnum():
            raise ValueError("whisper_language 必须是合法语言代码")
        candidate["whisper_language"] = language
    if "external_endpoint" in incoming:
        endpoint = str(incoming["external_endpoint"] or "").strip()
        candidate["external_endpoint"] = (
            _validate_url(endpoint, "external_endpoint") if endpoint else ""
        )
    if "online_audio_format" in incoming:
        audio_format = str(incoming["online_audio_format"] or "").strip().lower()
        if audio_format not in {"mp3", "wav"}:
            raise ValueError("online_audio_format 仅允许 mp3/wav")
        candidate["online_audio_format"] = audio_format
    if "cache_enabled" in incoming:
        raw_cache = incoming["cache_enabled"]
        if isinstance(raw_cache, bool):
            candidate["cache_enabled"] = raw_cache
        elif str(raw_cache).strip().lower() in {"true", "false", "1", "0"}:
            candidate["cache_enabled"] = str(raw_cache).strip().lower() in {"true", "1"}
        else:
            raise ValueError("cache_enabled 必须是布尔值")

    numeric_rules = {
        "bcut_timeout": (1.0, 600.0, float),
        "external_timeout": (1.0, 600.0, float),
        "vad_threshold_seconds": (30.0, 7200.0, float),
        "vad_target_segment_seconds": (10.0, 1800.0, float),
        "concurrency": (1, 3, int),
        "online_target_segment_seconds": (10.0, 295.0, float),
        "local_target_segment_seconds": (10.0, 1800.0, float),
        "online_concurrency": (1, 3, int),
        "local_concurrency": (1, 3, int),
        "online_audio_bitrate_kbps": (32, 128, int),
        "request_timeout": (1.0, 3600.0, float),
    }
    for key, (lower, upper, cast) in numeric_rules.items():
        if key not in incoming:
            continue
        if key == "vad_target_segment_seconds" and incoming[key] in (None, ""):
            candidate[key] = None
            continue
        try:
            value = cast(incoming[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} 必须是数字") from exc
        if not lower <= value <= upper:
            raise ValueError(f"{key} 取值越界（允许 {lower}~{upper}）")
        candidate[key] = value
    if "concurrency" in incoming:
        candidate["online_concurrency"] = candidate.pop("concurrency")
    if "vad_target_segment_seconds" in incoming:
        legacy_target = candidate.pop("vad_target_segment_seconds", None)
        if legacy_target is not None:
            candidate["online_target_segment_seconds"] = legacy_target
            candidate["local_target_segment_seconds"] = legacy_target
    return candidate


def _normalize_asr_config(value: Any) -> dict[str, Any]:
    """把旧 ``model_path`` 键收敛为当前公开契约并移除未知字段。"""
    config = parse_json_object(value)
    normalized = dict(_ASR_CONFIG_DEFAULTS)
    normalized.update({
        key: item
        for key, item in config.items()
        if key in _ASR_CONFIG_FIELDS and key not in {"concurrency", "vad_target_segment_seconds"}
    })
    if not normalized.get("whisper_model_path") and config.get("model_path"):
        normalized["whisper_model_path"] = config["model_path"]
    if "online_concurrency" not in config and config.get("concurrency") is not None:
        normalized["online_concurrency"] = config["concurrency"]
    if config.get("vad_target_segment_seconds") is not None:
        legacy_target = config["vad_target_segment_seconds"]
        if "online_target_segment_seconds" not in config:
            normalized["online_target_segment_seconds"] = legacy_target
        if "local_target_segment_seconds" not in config:
            normalized["local_target_segment_seconds"] = legacy_target
    return normalized


def _credential_target(provider: str, field: str) -> tuple[str, str]:
    normalized = str(provider or "").strip().lower()
    normalized_field = str(field or "").strip().lower()
    if normalized in PROVIDER_REGISTRY:
        allowed = frozenset(PROVIDER_REGISTRY[normalized].credential_fields)
        namespace, subject = "llm", normalized
    elif normalized in _SPECIAL_CREDENTIALS:
        namespace, subject, allowed = _SPECIAL_CREDENTIALS[normalized]
    else:
        raise ValueError("未知凭证槽位")
    if normalized_field not in allowed:
        raise ValueError("该凭证字段不允许读取或写入")
    return namespace, subject


def _masked(value: str) -> str:
    return f"••••••••{value[-4:]}" if len(value) >= 8 else "••••••••"


def _credential_value_and_source(provider: str, field: str) -> tuple[str, str]:
    namespace, subject = _credential_target(provider, field)
    store = CredentialStore()
    encrypted = store.get(namespace, subject, field)
    if encrypted:
        return str(encrypted), "encrypted"
    env_name = None
    if namespace == "llm":
        env_name = f"{subject.upper()}_{field.upper()}"
    elif provider == "external_asr":
        env_name = "EXTERNAL_ASR_API_KEY"
    elif provider == "bilibili":
        env_name = "BILIBILI_COOKIE"
    environment = os.environ.get(env_name or "")
    return (environment, "environment") if environment else ("", "none")


def _credential_state(provider: str, field: str) -> dict[str, Any]:
    value, source = _credential_value_and_source(provider, field)
    return {
        "configured": bool(value),
        "masked": _masked(value) if value else "",
        "source": source,
    }


def _settings_response(repo: Any) -> dict[str, Any]:
    snapshot = get_settings_snapshot(repo)
    profiles = provider_profiles(parse_json_object(snapshot.get("llm.providers")))
    public_settings = {
        key: value
        for key, value in snapshot.items()
        if key not in _INTERNAL_KEYS and key != "llm.providers"
    }
    public_settings["asr.config"] = _normalize_asr_config(
        public_settings.get("asr.config")
    )
    credentials = {
        provider: {
            field: _credential_state(provider, field)
            for field in definition.credential_fields
        }
        for provider, definition in PROVIDER_REGISTRY.items()
    }
    settings_store = SettingsStore()
    credential_store = CredentialStore()
    return {
        "settings": public_settings,
        "providers": public_provider_registry(),
        "profiles": profiles,
        "credentials": credentials,
        "sensitive": {
            "external_asr": {"api_key": _credential_state("external_asr", "api_key")},
            "bilibili": {"cookie": _credential_state("bilibili", "cookie")},
        },
        "storage": {
            "settings_path": str(settings_store.path),
            "credentials_path": str(credential_store.path),
            "master_key_source": credential_store.master_key_source,
        },
        "note": "设置只影响之后创建的任务；普通响应不包含凭证明文",
    }


@router.get("")
async def get_settings():
    return _settings_response(get_task_service().repo)


@router.put("")
async def update_settings(body: Dict[str, Any]):
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="请求体必须是 key→value 对象")
    if any(key in _INTERNAL_KEYS for key in body):
        raise HTTPException(status_code=400, detail="敏感字段必须使用凭证接口")

    repo = get_task_service().repo
    # 确保首次启动或旧库迁移已完成。
    snapshot = get_settings_snapshot(repo)
    store = SettingsStore()
    try:
        current = store.read() if store.exists() else {
            key: value
            for key, value in snapshot.items()
            if key not in _INTERNAL_KEYS
        }
    except SettingsFileError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    candidate = dict(current)
    updated: list[str] = []
    try:
        profiles = provider_profiles(
            parse_json_object(candidate.get("llm.providers") or snapshot.get("llm.providers"))
        )
        for key, value in body.items():
            if key == "llm.providers":
                profiles = _validate_profiles(value, profiles)
                candidate[key] = profiles
                updated.append(key)
                continue
            if key == "asr.config":
                if isinstance(value, dict) and any(
                    name in value for name in ("external_api_key", "api_key")
                ):
                    raise ValueError("外部 ASR API Key 必须使用凭证接口")
                existing = parse_json_object(candidate.get(key))
                candidate[key] = _validate_asr_config(value, existing)
                updated.append(key)
                continue
            stored = _validate_scalar(key, value)
            if stored is not None:
                candidate[key] = stored
                updated.append(key)

        if "llm.provider" in body and "llm.model" not in body:
            selected = candidate["llm.provider"]
            candidate["llm.model"] = profiles[selected]["model"]
        candidate["llm.providers"] = profiles
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        store.write(candidate)
    except SettingsFileError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    response = _settings_response(repo)
    response["updated"] = updated
    return response


@router.put("/credentials")
async def save_credential(body: Dict[str, Any]):
    provider = str(body.get("provider") or "").strip().lower()
    field = str(body.get("field") or "").strip().lower()
    try:
        namespace, subject = _credential_target(provider, field)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    value = body.get("value")
    # 空输入代表“保持原值”；清除必须走显式 DELETE。
    if value not in (None, ""):
        text = str(value)
        if len(text) > 16_384:
            raise HTTPException(status_code=400, detail="凭证长度超出限制")
        CredentialStore().update_fields(namespace, subject, {field: text})
    return {"state": _credential_state(provider, field)}


@router.post("/credentials/reveal")
async def reveal_credential(body: Dict[str, Any], response: Response):
    provider = str(body.get("provider") or "").strip().lower()
    field = str(body.get("field") or "").strip().lower()
    try:
        _credential_target(provider, field)
        value, _source = _credential_value_and_source(provider, field)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not value:
        raise HTTPException(status_code=404, detail="该凭证尚未配置")
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return {"value": value}


@router.delete("/credentials/{provider}/{field}")
async def clear_credential(provider: str, field: str):
    try:
        namespace, subject = _credential_target(provider, field)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store = CredentialStore()
    removed = store.clear_field(namespace, subject, field)
    if not removed:
        _value, source = _credential_value_and_source(provider, field)
        if source == "environment":
            raise HTTPException(
                status_code=409,
                detail="该凭证来自环境变量，请在部署配置中清除",
            )
    return {"state": _credential_state(provider, field)}


@router.post("/llm/test")
async def test_llm_connection(body: Dict[str, Any]):
    """仅在用户主动触发时发送一个极小的真实 Chat Completions 请求。"""
    provider = str(body.get("provider") or "").strip().lower()
    if provider not in PROVIDER_REGISTRY:
        raise HTTPException(status_code=400, detail="未知 LLM provider")
    repo = get_task_service().repo
    snapshot = get_settings_snapshot(repo)
    profiles = provider_profiles(parse_json_object(snapshot.get("llm.providers")))
    profile = profiles[provider]
    definition = PROVIDER_REGISTRY[provider]
    if definition.requires_model and not profile.get("model"):
        raise HTTPException(status_code=400, detail="请先填写模型 ID")
    if definition.requires_base_url and not profile.get("base_url"):
        raise HTTPException(status_code=400, detail="请先填写 Base URL")

    api_key = ""
    if "api_key" in definition.credential_fields:
        api_key, _source = _credential_value_and_source(provider, "api_key")
        if not api_key and provider != "custom":
            raise HTTPException(status_code=400, detail="请先填写 API Key")
    config = {
        "api_key": api_key,
        "model": profile["model"],
        "base_url": profile["base_url"],
        "timeout": profile["timeout"],
    }
    started = time.monotonic()
    try:
        llm = LLMFactory.create(provider, config)
        answer = llm.chat(
            [{"role": "user", "content": "Reply only with OK."}],
            max_tokens=8,
            timeout=profile["timeout"],
        )
        if not str(answer or "").strip():
            return {
                "ok": False,
                "category": "invalid_response",
                "message": "服务已响应，但返回内容为空",
            }
        return {
            "ok": True,
            "category": "success",
            "message": "连接成功",
            "latency_ms": round((time.monotonic() - started) * 1000),
        }
    except Exception as exc:  # 响应只返回分类后的安全文案，不回显 SDK 错误/密钥
        message = str(exc).lower()
        if isinstance(exc, TimeoutError) or "timeout" in message or "超时" in message:
            category, safe_message = "timeout", "连接超时，请检查地址、网络和超时设置"
        elif any(token in message for token in ("401", "403", "unauthorized", "认证", "鉴权")):
            category, safe_message = "authentication", "鉴权失败，请检查 API Key"
        elif any(token in message for token in ("model", "模型", "404")):
            category, safe_message = "model", "模型不可用，请检查模型 ID"
        else:
            category, safe_message = "connection", "连接失败，请检查服务地址和网络"
        return {"ok": False, "category": category, "message": safe_message}
