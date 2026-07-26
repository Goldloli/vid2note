"""``GET/PUT /api/v1/settings`` —— 设置读写(契约 §3.2 / §4.1)。

数据源:SQLite ``settings`` 表(权威态)。GET 返回全部 key(凭证脱敏);
PUT 逐项校验,非法值拒 400,合法值立即持久化。**仅对新任务生效**(create_task 在
创建时读快照,历史任务不受影响)。
"""
import json
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from src.runtime.settings import get_settings_snapshot
from src.runtime.task_service import get_task_service
from src.utils.security import secure_filename  # noqa: F401  (保留供扩展使用)

router = APIRouter(prefix="/settings", tags=["settings"])


# 凭证类 key:GET 时脱敏,PUT 时若收到掩码值则跳过(避免覆盖真实凭证)
SENSITIVE_KEYS = frozenset({"llm.credentials", "bilibili.cookie", "asr.config"})
_MASK = "***"

# 各 key 的合法枚举集合(契约 §3.2)
_ENUM_ALLOWED: Dict[str, frozenset] = {
    "asr.engine": frozenset({"asrtools", "whisper_cpp", "external"}),
    "asr.strategy": frozenset({"online_first", "single"}),
    "pdf.mode": frozenset({"pypdf", "mineru"}),
    "note.output_language": frozenset({"zh", "en"}),
    "note.image_quality": frozenset({"low", "medium", "high"}),
    "retention.video": frozenset({"permanent", "7d", "30d"}),
    "retention.audio": frozenset({"permanent", "7d", "30d"}),
    "retention.srt": frozenset({"permanent", "7d", "30d"}),
    "retention.note": frozenset({"permanent", "7d", "30d"}),
    "retention.screenshot": frozenset({"permanent", "7d", "30d"}),
}

# 数值类 key:(key, cast, min, max)
_NUMERIC_FIELDS = (
    ("concurrency.max", int, 1, 3),       # 契约 §0.8:1~3
    ("advanced.chunk_size", int, 1, 1_000_000),
    ("advanced.max_retries", int, 0, 20),
)

# 浮点类 key:(key, min, max)
_FLOAT_FIELDS = (
    ("advanced.temperature", 0.0, 2.0),
)

# 布尔类 key
_BOOL_KEYS = frozenset({"note.extract_images"})

# JSON 对象类 key(存前 json.dumps)
_JSON_KEYS = frozenset({"llm.credentials", "bilibili.cookie", "asr.config"})


def _mask_value(key: str, raw: str) -> Any:
    """凭证类 key 脱敏:已配置返回 ``***``,空值返回空串。"""
    if key in SENSITIVE_KEYS:
        if raw is None or raw in ("", "{}"):
            return ""
        return _MASK
    return raw


def _validate_and_coerce(key: str, value: Any) -> str:
    """逐项校验单个 key 的取值;非法 raise ValueError(中文),合法返回待存字符串。

    复杂值(dict/list)在合法时 ``json.dumps`` 为字符串(契约 §3.2:复杂值存 JSON)。
    """
    # 未知 key:忽略(返回 None 表示不写入)
    known = (
        key in _ENUM_ALLOWED
        or any(k == key for k, *_ in _NUMERIC_FIELDS)
        or any(k == key for k, *_ in _FLOAT_FIELDS)
        or key in _BOOL_KEYS
        or key in _JSON_KEYS
        or key in {"llm.provider", "llm.model", "pdf.mineru_endpoint"}
    )
    if not known:
        return None  # type: ignore[return-value]

    # 凭证掩码回传:跳过(不覆盖)
    if key in SENSITIVE_KEYS and isinstance(value, str) and value == _MASK:
        return None  # type: ignore[return-value]

    # 布尔类
    if key in _BOOL_KEYS:
        s = str(value).strip().lower() if value is not None else ""
        if s not in ("true", "false", "1", "0", "yes", "no", "on", "off"):
            raise ValueError(f"{key} 必须是布尔值(true/false)")
        return "true" if s in ("true", "1", "yes", "on") else "false"

    # 数值整型类
    for k, cast, lo, hi in _NUMERIC_FIELDS:
        if key == k:
            try:
                n = cast(value)
            except (TypeError, ValueError):
                raise ValueError(f"{key} 必须是整数")
            if n < lo or n > hi:
                raise ValueError(f"{key} 取值越界(允许 {lo}~{hi})")
            return str(n)

    # 浮点类
    for k, lo, hi in _FLOAT_FIELDS:
        if key == k:
            try:
                f = float(value)
            except (TypeError, ValueError):
                raise ValueError(f"{key} 必须是数字")
            if f < lo or f > hi:
                raise ValueError(f"{key} 取值越界(允许 {lo}~{hi})")
            return str(f)

    # 枚举类
    if key in _ENUM_ALLOWED:
        allowed = _ENUM_ALLOWED[key]
        s = str(value).strip().lower() if value is not None else ""
        if s not in allowed:
            raise ValueError(f"{key} 非法取值:{value}(允许 {sorted(allowed)})")
        return s

    # JSON 对象类(凭证):接受 dict/list 或 JSON 字符串
    if key in _JSON_KEYS:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, str):
            try:
                obj = json.loads(value)
            except (ValueError, TypeError):
                raise ValueError(f"{key} 不是合法的 JSON")
            return json.dumps(obj if isinstance(obj, (dict, list)) else value, ensure_ascii=False)
        raise ValueError(f"{key} 必须是 JSON 对象或字符串")

    # 自由文本类(llm.provider / llm.model / pdf.mineru_endpoint)
    s = str(value).strip() if value is not None else ""
    if key in {"llm.provider", "llm.model"} and not s:
        raise ValueError(f"{key} 不能为空")
    return s


@router.get("")
async def get_settings():
    """读取全部设置(凭证字段脱敏)。"""
    repo = get_task_service().repo
    snapshot = get_settings_snapshot(repo)
    return {
        "settings": {key: _mask_value(key, val) for key, val in snapshot.items()},
        "note": "凭证类字段(llm.credentials / bilibili.cookie / asr.config)已脱敏",
    }


@router.put("")
async def update_settings(body: Dict[str, Any]):
    """逐项校验并更新设置(仅对新任务生效)。

    body 为 ``key→value`` 子集;逐项校验,任一非法即整体拒绝(400,中文错误),
    不写入任何值。合法值立即持久化,对下一次清理扫描与新任务生效。
    """
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="请求体必须是 key→value 对象")

    repo = get_task_service().repo
    # 先全部校验,再统一写入(原子语义:任一非法都不落库)
    pending: list[tuple[str, str]] = []
    for key, value in body.items():
        try:
            stored = _validate_and_coerce(key, value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if stored is not None:
            pending.append((key, stored))

    for key, stored in pending:
        repo.set_setting(key, stored)

    snapshot = get_settings_snapshot(repo)
    return {
        "updated": [k for k, _ in pending],
        "settings": {key: _mask_value(key, val) for key, val in snapshot.items()},
        "note": "设置仅对在此之后创建的任务生效",
    }
