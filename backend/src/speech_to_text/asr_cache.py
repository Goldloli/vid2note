"""ASR 结果文件级缓存（crc32 键），借鉴 社区 bcut 参考项目 ``BaseASR``。

同一份音频（字节级相同）在同一引擎与语言下命中缓存时直接返回转录结果，跳过在线
上传与轮询。缓存键包含引擎名、音频字节 crc32 与语言，内容不同的音频不会命中。

缓存仅为加速，MUST NOT 阻断转录：读写失败只告警、不抛异常。
"""
from __future__ import annotations

import json
import logging
import os
import zlib
from typing import Optional

from .engine import Cue

_LOGGER = logging.getLogger("speech_to_text.asr_cache")


def cache_key(engine: str, audio_bytes: bytes, lang: str = "") -> str:
    """构建缓存键 ``{engine}-{crc32:08x}-{lang}``。字节级相同即同键。"""
    crc = zlib.crc32(audio_bytes) & 0xFFFFFFFF
    return f"{engine}-{crc:08x}-{lang or 'default'}"


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
        cues = [
            Cue(start=float(c["start"]), end=float(c["end"]), text=str(c.get("text", "")).strip())
            for c in (data or [])
            if c.get("text", "").strip()
        ]
        _LOGGER.info("ASR 缓存命中 key=%s cues=%d", key, len(cues))
        return cues
    except (ValueError, KeyError, OSError, TypeError) as exc:
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
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)  # 原子替换，避免半写文件被读为命中
    except OSError as exc:
        _LOGGER.warning("ASR 缓存写入失败 key=%s：%s", key, exc)
