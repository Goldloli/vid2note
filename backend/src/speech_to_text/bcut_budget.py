"""bcut 公益接口的本地滚动额度保护。

公开参考客户端把 bcut 使用限制为 12 小时最多 100 次、累计音频最多 360 分钟。
这里在整项任务开始前一次性预留预算，避免长视频做到一半才因 412 切换到本地引擎，
从而生成识别风格混杂的字幕。额度文件位于持久化 ASR 缓存目录，并用文件锁保护
多任务并发与容器重启场景。
"""
from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Iterator, Optional

import fcntl


BUDGET_SCHEMA = 1
WINDOW_SECONDS = 12 * 60 * 60
MAX_CALLS = 100
MAX_AUDIO_SECONDS = 360 * 60
_BUDGET_FILE = "bcut-budget-v1.json"
_LOCK_FILE = "bcut-budget-v1.lock"
_COOLDOWN_FILE = "bcut-remote-cooldown-v1.json"
_PROCESS_LOCK = threading.RLock()
_PROCESS_COOLDOWN_UNTIL = 0.0


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    tracked: bool
    requested_calls: int
    requested_audio_seconds: float
    used_calls: int
    used_audio_seconds: float
    remaining_calls: int
    remaining_audio_seconds: float
    retry_after_seconds: float
    reason: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in (
            "requested_audio_seconds",
            "used_audio_seconds",
            "remaining_audio_seconds",
            "retry_after_seconds",
        ):
            data[key] = round(float(data[key]), 3)
        return data


@contextmanager
def _locked(cache_dir: str) -> Iterator[None]:
    os.makedirs(cache_dir, exist_ok=True)
    lock_path = os.path.join(cache_dir, _LOCK_FILE)
    with _PROCESS_LOCK, open(lock_path, "a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _load_entries(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or payload.get("schema_version") != BUDGET_SCHEMA:
        raise ValueError("bcut 额度文件 schema 不兼容")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError("bcut 额度文件 entries 非列表")
    normalized: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("bcut 额度记录结构非法")
        timestamp = float(entry["timestamp"])
        calls = int(entry["calls"])
        audio_seconds = float(entry["audio_seconds"])
        if timestamp < 0 or calls < 0 or audio_seconds < 0:
            raise ValueError("bcut 额度记录含负数")
        normalized.append({
            "timestamp": timestamp,
            "calls": calls,
            "audio_seconds": audio_seconds,
        })
    return normalized


def _write_entries(path: str, entries: list[dict]) -> None:
    payload = {"schema_version": BUDGET_SCHEMA, "entries": entries}
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _load_cooldown(path: str) -> float:
    if not os.path.exists(path):
        return 0.0
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or payload.get("schema_version") != BUDGET_SCHEMA:
        raise ValueError("bcut 冷却文件 schema 不兼容")
    blocked_until = float(payload.get("blocked_until", 0.0))
    if blocked_until < 0:
        raise ValueError("bcut 冷却截止时间不能为负数")
    return blocked_until


def _write_cooldown(path: str, blocked_until: float) -> None:
    payload = {
        "schema_version": BUDGET_SCHEMA,
        "blocked_until": max(0.0, float(blocked_until)),
    }
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def mark_rate_limited(
    cache_dir: Optional[str],
    *,
    retry_after_seconds: float = WINDOW_SECONDS,
    now: Optional[float] = None,
) -> float:
    """记录远端真实 412/429 冷却，并返回冷却截止时间。

    进程态用于当前容器内立即熔断；独立文件用于容器重启后继续生效。写文件失败时
    仍保留进程态，避免同一轮任务继续撞远端。
    """
    global _PROCESS_COOLDOWN_UNTIL
    current = time.time() if now is None else float(now)
    blocked_until = current + max(1.0, float(retry_after_seconds))
    with _PROCESS_LOCK:
        _PROCESS_COOLDOWN_UNTIL = max(_PROCESS_COOLDOWN_UNTIL, blocked_until)
    if not cache_dir:
        return _PROCESS_COOLDOWN_UNTIL

    path = os.path.join(cache_dir, _COOLDOWN_FILE)
    try:
        with _locked(cache_dir):
            persisted = _load_cooldown(path)
            blocked_until = max(blocked_until, persisted, _PROCESS_COOLDOWN_UNTIL)
            _PROCESS_COOLDOWN_UNTIL = blocked_until
            _write_cooldown(path, blocked_until)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        pass
    return _PROCESS_COOLDOWN_UNTIL


def cooldown_remaining(
    cache_dir: Optional[str], *, now: Optional[float] = None
) -> float:
    """返回远端限流冷却剩余秒数；冷却文件损坏时安全熔断一个窗口。"""
    global _PROCESS_COOLDOWN_UNTIL
    current = time.time() if now is None else float(now)
    with _PROCESS_LOCK:
        blocked_until = _PROCESS_COOLDOWN_UNTIL
    if cache_dir:
        path = os.path.join(cache_dir, _COOLDOWN_FILE)
        try:
            with _locked(cache_dir):
                blocked_until = max(blocked_until, _load_cooldown(path))
                _PROCESS_COOLDOWN_UNTIL = blocked_until
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            blocked_until = mark_rate_limited(cache_dir, now=current)
    return max(0.0, blocked_until - current)


def _prune(entries: list[dict], now: float) -> list[dict]:
    cutoff = now - WINDOW_SECONDS
    return sorted(
        (entry for entry in entries if entry["timestamp"] > cutoff),
        key=lambda entry: entry["timestamp"],
    )


def _retry_after(
    entries: list[dict], requested_calls: int, requested_audio_seconds: float, now: float
) -> float:
    calls = sum(entry["calls"] for entry in entries)
    audio_seconds = sum(entry["audio_seconds"] for entry in entries)
    for entry in entries:
        calls -= entry["calls"]
        audio_seconds -= entry["audio_seconds"]
        if calls + requested_calls <= MAX_CALLS and audio_seconds + requested_audio_seconds <= MAX_AUDIO_SECONDS:
            return max(0.0, entry["timestamp"] + WINDOW_SECONDS - now)
    return float(WINDOW_SECONDS)


def _decision(
    entries: list[dict], requested_calls: int, requested_audio_seconds: float, now: float
) -> BudgetDecision:
    used_calls = sum(entry["calls"] for entry in entries)
    used_audio_seconds = sum(entry["audio_seconds"] for entry in entries)
    allowed = (
        used_calls + requested_calls <= MAX_CALLS
        and used_audio_seconds + requested_audio_seconds <= MAX_AUDIO_SECONDS
    )
    reserved_calls = requested_calls if allowed else 0
    reserved_audio_seconds = requested_audio_seconds if allowed else 0.0
    return BudgetDecision(
        allowed=allowed,
        tracked=True,
        requested_calls=requested_calls,
        requested_audio_seconds=requested_audio_seconds,
        used_calls=used_calls,
        used_audio_seconds=used_audio_seconds,
        remaining_calls=max(0, MAX_CALLS - used_calls - reserved_calls),
        remaining_audio_seconds=max(
            0.0, MAX_AUDIO_SECONDS - used_audio_seconds - reserved_audio_seconds
        ),
        retry_after_seconds=(
            0.0 if allowed else _retry_after(entries, requested_calls, requested_audio_seconds, now)
        ),
        reason="" if allowed else "rolling_budget_exceeded",
    )


def reserve(
    cache_dir: Optional[str], *, calls: int, audio_seconds: float, now: Optional[float] = None
) -> BudgetDecision:
    """原子预留整项任务预算；跟踪不可用时安全拒绝在线公益接口。"""
    requested_calls = max(1, int(calls))
    requested_audio_seconds = max(0.0, float(audio_seconds))
    current = time.time() if now is None else float(now)
    cooldown = cooldown_remaining(cache_dir, now=current)
    if cooldown > 0:
        return BudgetDecision(
            allowed=False,
            tracked=bool(cache_dir),
            requested_calls=requested_calls,
            requested_audio_seconds=requested_audio_seconds,
            used_calls=0,
            used_audio_seconds=0.0,
            remaining_calls=0,
            remaining_audio_seconds=0.0,
            retry_after_seconds=cooldown,
            reason="remote_rate_limited",
        )
    if not cache_dir:
        return BudgetDecision(
            allowed=True,
            tracked=False,
            requested_calls=requested_calls,
            requested_audio_seconds=requested_audio_seconds,
            used_calls=0,
            used_audio_seconds=0.0,
            remaining_calls=MAX_CALLS,
            remaining_audio_seconds=float(MAX_AUDIO_SECONDS),
            retry_after_seconds=0.0,
            reason="tracking_disabled",
        )
    path = os.path.join(cache_dir, _BUDGET_FILE)
    try:
        with _locked(cache_dir):
            entries = _prune(_load_entries(path), current)
            decision = _decision(entries, requested_calls, requested_audio_seconds, current)
            if decision.allowed:
                entries.append({
                    "timestamp": current,
                    "calls": requested_calls,
                    "audio_seconds": requested_audio_seconds,
                })
            _write_entries(path, entries)
            return decision
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return BudgetDecision(
            allowed=False,
            tracked=False,
            requested_calls=requested_calls,
            requested_audio_seconds=requested_audio_seconds,
            used_calls=0,
            used_audio_seconds=0.0,
            remaining_calls=0,
            remaining_audio_seconds=0.0,
            retry_after_seconds=float(WINDOW_SECONDS),
            reason="tracking_unavailable",
        )


def snapshot(cache_dir: Optional[str], *, now: Optional[float] = None) -> BudgetDecision:
    """只读返回当前滚动额度，不预留调用。"""
    current = time.time() if now is None else float(now)
    cooldown = cooldown_remaining(cache_dir, now=current)
    if cooldown > 0:
        return BudgetDecision(
            allowed=False,
            tracked=bool(cache_dir),
            requested_calls=0,
            requested_audio_seconds=0.0,
            used_calls=0,
            used_audio_seconds=0.0,
            remaining_calls=0,
            remaining_audio_seconds=0.0,
            retry_after_seconds=cooldown,
            reason="remote_rate_limited",
        )
    if not cache_dir:
        return BudgetDecision(
            allowed=True,
            tracked=False,
            requested_calls=0,
            requested_audio_seconds=0.0,
            used_calls=0,
            used_audio_seconds=0.0,
            remaining_calls=MAX_CALLS,
            remaining_audio_seconds=float(MAX_AUDIO_SECONDS),
            retry_after_seconds=0.0,
            reason="tracking_disabled",
        )
    path = os.path.join(cache_dir, _BUDGET_FILE)
    try:
        with _locked(cache_dir):
            entries = _prune(_load_entries(path), current)
            _write_entries(path, entries)
            probe = _decision(entries, 1, 1.0, current)
            return BudgetDecision(
                allowed=probe.allowed,
                tracked=True,
                requested_calls=0,
                requested_audio_seconds=0.0,
                used_calls=probe.used_calls,
                used_audio_seconds=probe.used_audio_seconds,
                remaining_calls=max(0, MAX_CALLS - probe.used_calls),
                remaining_audio_seconds=max(
                    0.0, MAX_AUDIO_SECONDS - probe.used_audio_seconds
                ),
                retry_after_seconds=probe.retry_after_seconds,
                reason=probe.reason,
            )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return BudgetDecision(
            allowed=False,
            tracked=False,
            requested_calls=0,
            requested_audio_seconds=0.0,
            used_calls=0,
            used_audio_seconds=0.0,
            remaining_calls=0,
            remaining_audio_seconds=0.0,
            retry_after_seconds=float(WINDOW_SECONDS),
            reason="tracking_unavailable",
        )
