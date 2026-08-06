"""ASR 结果文件级缓存。

分段缓存保留轻量 crc32 键；整段缓存使用流式 sha256，并把引擎、语言、缓存 schema
和影响结果的配置档案纳入键。整段命中发生在 VAD 之前，可跳过切片、上传和轮询。

缓存仅为加速，MUST NOT 阻断转录：读写失败只告警、不抛异常。
"""
from __future__ import annotations

import json
import hashlib
import logging
import os
import threading
import zlib
from typing import Optional

from .engine import Cue

_LOGGER = logging.getLogger("speech_to_text.asr_cache")
WHOLE_CACHE_SCHEMA = "whole-v2"


def cache_key(engine: str, audio_bytes: bytes, lang: str = "") -> str:
    """构建缓存键 ``{engine}-{crc32:08x}-{lang}``。字节级相同即同键。"""
    crc = zlib.crc32(audio_bytes) & 0xFFFFFFFF
    return f"{engine}-{crc:08x}-{lang or 'default'}"


def whole_file_cache_key(
    engine_profile: str,
    audio_path: str,
    *,
    lang: str = "",
    result_profile: str = "",
) -> str:
    """为整段音频构建强内容哈希键；读取采用固定块，避免把大 WAV 一次载入内存。"""
    digest = hashlib.sha256()
    for part in (WHOLE_CACHE_SCHEMA, engine_profile, lang or "default", result_profile):
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    with open(audio_path, "rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return f"{WHOLE_CACHE_SCHEMA}-{digest.hexdigest()}"


def _cache_path(cache_dir: str, key: str) -> str:
    return os.path.join(cache_dir, f"{key}.json")


def get(cache_dir: Optional[str], key: str) -> Optional[list[Cue]]:
    """命中返回 cues；未命中、禁用或读取失败返回 None。"""
    if not cache_dir:
        return None
    path = _cache_path(cache_dir, key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise ValueError("缓存根节点或 Cue 结构非法")
        cues = [
            Cue(start=float(c["start"]), end=float(c["end"]), text=str(c.get("text", "")).strip())
            for c in (data or [])
            if c.get("text", "").strip()
        ]
        _LOGGER.info("ASR 缓存命中 key=%s cues=%d", key, len(cues))
        return cues
    except (ValueError, KeyError, OSError, TypeError, AttributeError) as exc:
        _LOGGER.warning("ASR 缓存读取失败 key=%s：%s", key, exc)
        return None


def put(cache_dir: Optional[str], key: str, cues: list[Cue]) -> None:
    """写缓存；失败只告警，MUST NOT 抛异常阻断转录。"""
    if not cache_dir:
        return
    try:
        os.makedirs(cache_dir, exist_ok=True)
        path = _cache_path(cache_dir, key)
        data = [{"start": c.start, "end": c.end, "text": c.text} for c in cues]
        tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)  # 原子替换，避免半写文件被读为命中
    except OSError as exc:
        _LOGGER.warning("ASR 缓存写入失败 key=%s：%s", key, exc)
