"""
runtime.settings —— 设置快照与合法默认值(契约 §3.2 / §0.8)
============================================================

把 SQLite ``settings`` 表的扁平 key/value 读出为一份**强类型快照**供运行栈使用;
首次启动(settings 表为空或部分 key 缺失)MUST 给出合法默认值
(spec storage-retention「首次启动写入合法默认」)。

默认值(契约 §3.2):
- LLM = deepseek / deepseek-v4-flash
- ASR = asrtools(策略 online_first)
- PDF = pypdf
- 并发 = 1(范围 1~3,越界回落 1)
- 五类保留:video/audio=7d、srt/screenshot=30d、note=permanent
- 输出语言 = zh、截图嵌入 = 关

本模块只做「读 + 补默认 + 校验回落」,不写库;写库由设置 API 负责。
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from src.core.kernel import logger

# --------------------------------------------------------------------------- #
# 合法默认值(契约 §3.2)
# --------------------------------------------------------------------------- #
DEFAULT_SETTINGS: Dict[str, str] = {
    # LLM
    "llm.provider": "deepseek",
    "llm.model": "deepseek-v4-flash",
    "llm.credentials": "{}",
    # ASR
    "asr.engine": "asrtools",
    "asr.strategy": "online_first",
    "asr.config": "{}",
    # PDF
    "pdf.mode": "pypdf",
    "pdf.mineru_endpoint": "",
    # Bilibili
    "bilibili.cookie": "{}",
    # 并发(契约 §0.8:默认 1,范围 1~3)
    "concurrency.max": "1",
    # 笔记
    "note.output_language": "zh",
    "note.extract_images": "false",
    "note.image_quality": "medium",
    # 五类保留策略(契约 §3.2 建议)
    "retention.video": "7d",
    "retention.audio": "7d",
    "retention.srt": "30d",
    "retention.note": "permanent",
    "retention.screenshot": "30d",
    # 高级参数
    "advanced.chunk_size": "4000",
    "advanced.temperature": "0.3",
    "advanced.max_retries": "3",
}

# 并发合法范围(契约 §0.8)
MIN_CONCURRENCY = 1
MAX_CONCURRENCY = 3
DEFAULT_CONCURRENCY = 1

# 保留策略合法枚举
_RETENTION_VALUES = frozenset({"permanent", "7d", "30d"})
# 输出语言合法枚举
_LANGUAGES = frozenset({"zh", "en"})
# PDF 方案合法枚举
_PDF_MODES = frozenset({"pypdf", "mineru"})
# ASR 引擎合法枚举
_ASR_ENGINES = frozenset({"asrtools", "whisper_cpp", "external"})


def clamp_concurrency(value: Any) -> int:
    """把任意值归一为合法并发数(1~3);越界/非法回落默认 1(契约 §0.8)。"""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return DEFAULT_CONCURRENCY
    if n < MIN_CONCURRENCY:
        return MIN_CONCURRENCY
    if n > MAX_CONCURRENCY:
        return MAX_CONCURRENCY
    return n


def _coerce_enum(value: Any, allowed: frozenset[str], default: str) -> str:
    """枚举值校验:非法回落 default。"""
    s = str(value).strip().lower() if value is not None else ""
    return s if s in allowed else default


def get_settings_snapshot(repo: Any = None) -> Dict[str, str]:
    """读取全部设置并以合法默认值补齐缺失项。

    Args:
        repo: ``TaskRepository``(或任何带 ``get_all_settings()`` 的对象);
            ``None`` 时仅返回默认值(便于无库单测)。

    Returns:
        扁平 ``key→value`` 字符串快照(已补默认 + 枚举回落)。
    """
    raw: Dict[str, str] = {}
    if repo is not None:
        try:
            raw = dict(repo.get_all_settings() or {})
        except Exception:  # noqa: BLE001 - 读库失败不阻断运行
            logger.debug("读取 settings 失败,回落默认值", exc_info=True)
            raw = {}

    snapshot: Dict[str, str] = dict(DEFAULT_SETTINGS)
    # 用库中实际值覆盖默认(仅覆盖存在的 key)
    for k, v in raw.items():
        if v is None:
            continue
        snapshot[k] = str(v)

    # 枚举类 key 的合法性回落(非法取值不改库,仅本快照内回落)
    snapshot["llm.provider"] = (snapshot.get("llm.provider") or "deepseek").strip().lower() or "deepseek"
    snapshot["llm.model"] = (snapshot.get("llm.model") or "deepseek-v4-flash").strip() or "deepseek-v4-flash"
    snapshot["asr.engine"] = _coerce_enum(snapshot.get("asr.engine"), _ASR_ENGINES, "asrtools")
    snapshot["asr.strategy"] = _coerce_enum(
        snapshot.get("asr.strategy"), frozenset({"online_first", "single"}), "online_first"
    )
    snapshot["pdf.mode"] = _coerce_enum(snapshot.get("pdf.mode"), _PDF_MODES, "pypdf")
    snapshot["note.output_language"] = _coerce_enum(
        snapshot.get("note.output_language"), _LANGUAGES, "zh"
    )
    snapshot["note.extract_images"] = "true" if _as_bool(snapshot.get("note.extract_images")) else "false"
    for k in (
        "retention.video",
        "retention.audio",
        "retention.srt",
        "retention.note",
        "retention.screenshot",
    ):
        snapshot[k] = _coerce_enum(snapshot.get(k), _RETENTION_VALUES, DEFAULT_SETTINGS[k])
    return snapshot


def _as_bool(value: Any) -> bool:
    """把字符串/布尔/数字归一为布尔;空/非法为 False。"""
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower() if value is not None else ""
    return s in ("1", "true", "yes", "on")


def get_credentials(snapshot: Dict[str, str], provider: str) -> Dict[str, Any]:
    """从快照解析指定 provider 的凭证字典。

    ``llm.credentials`` 存 JSON,支持两种聚合形态:
    - 按 provider 聚合:``{"deepseek": {"api_key":..., "base_url":..., "model":...}}``
    - 扁平:``{"api_key":..., "base_url":...}``(视作当前 provider 的凭证)

    解析失败回落空字典,不抛错。
    """
    raw = snapshot.get("llm.credentials") or "{}"
    try:
        creds = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
    except (ValueError, TypeError):
        logger.debug("llm.credentials 解析失败,回落空凭证", exc_info=True)
        return {}
    if not isinstance(creds, dict):
        return {}
    if provider in creds and isinstance(creds[provider], dict):
        return dict(creds[provider])
    # 扁平形态:去掉可能存在的 provider 子键后整体返回
    flat = {k: v for k, v in creds.items() if k in creds and not isinstance(v, (dict, list))}
    return flat


__all__ = [
    "DEFAULT_SETTINGS",
    "MIN_CONCURRENCY",
    "MAX_CONCURRENCY",
    "DEFAULT_CONCURRENCY",
    "clamp_concurrency",
    "get_settings_snapshot",
    "get_credentials",
]
