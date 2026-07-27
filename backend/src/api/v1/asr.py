"""``GET/POST /api/v1/asr`` —— ASR 引擎状态与连通性测试(openspec change asr-management-page)。

- ``GET /asr/status``:三引擎就绪态(读 settings + 文件系统检查,无副作用,秒回)。
- ``POST /asr/test {engine}``:连通性测试——线上免费接口探活签名服务 / whisper 检查模型 / external
  探活 endpoint,统一返回 ``{ok, latency_ms, message}``。**不做真实音频转录**(v1 边界)。

端点用同步 ``def``(非 async):内部用同步 ``requests``,FastAPI 自动放线程池执行,不阻塞事件循环。
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Tuple

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.runtime.settings import get_settings_snapshot
from src.runtime.task_service import get_task_service
from src.speech_to_text.pipeline import AsrConfig

router = APIRouter(prefix="/asr", tags=["asr"])

_ENGINES = frozenset({"asrtools", "whisper_cpp", "external"})
_PROBE_TIMEOUT = 8.0


class AsrTestRequest(BaseModel):
    engine: str


def _asr_config() -> AsrConfig:
    """从 SQLite settings 快照构造当前 ASR 配置。"""
    repo = get_task_service().repo
    return AsrConfig.from_settings(get_settings_snapshot(repo))


@router.get("/status")
def asr_status() -> Dict[str, Any]:
    """三引擎就绪态(无副作用)。"""
    cfg = _asr_config()
    model_exists = bool(cfg.whisper_model_path) and os.path.exists(cfg.whisper_model_path)
    endpoint_configured = bool(cfg.external_endpoint)
    return {
        "asrtools": {
            "available": True,  # 在线引擎恒可用,实际可达性由 /test 探活
            "provider": cfg.asrtools_provider,
            "sign_endpoint": cfg.asrtools_sign_endpoint,
        },
        "whisper_cpp": {
            "available": model_exists,
            "model_exists": model_exists,
            "model_path": cfg.whisper_model_path,
        },
        "external": {
            "available": endpoint_configured,
            "endpoint_configured": endpoint_configured,
            "endpoint": cfg.external_endpoint or "",
        },
    }


@router.post("/test")
def asr_test(req: AsrTestRequest) -> Dict[str, Any]:
    """连通性测试(非真实转录):探活 / 模型可加载,返回 {ok, latency_ms, message}。"""
    engine = (req.engine or "").strip().lower()
    if engine not in _ENGINES:
        raise HTTPException(status_code=400, detail=f"不支持的引擎:{engine}(允许 asrtools/whisper_cpp/external)")
    cfg = _asr_config()
    start = time.perf_counter()
    try:
        if engine == "asrtools":
            ok, msg = _probe_online(cfg)
        elif engine == "whisper_cpp":
            ok, msg = _probe_whisper(cfg)
        else:
            ok, msg = _probe_external(cfg)
    except Exception as e:  # noqa: BLE001 - 探活任何异常都转为失败结果,不抛 500
        ok, msg = False, f"测试异常:{e}"
    return {
        "engine": engine,
        "ok": ok,
        "latency_ms": int((time.perf_counter() - start) * 1000),
        "message": msg,
    }


def _probe_online(cfg: AsrConfig) -> Tuple[bool, str]:
    """对线上免费接口签名服务发轻量 POST 探活(不传音频)。"""
    data = {"url": "/", "current_time": str(int(time.time())), "pf": "4", "appvr": "4.0.0", "tdid": "0" * 12}
    try:
        resp = requests.post(cfg.asrtools_sign_endpoint, json=data, timeout=_PROBE_TIMEOUT)
    except requests.exceptions.Timeout:
        return False, "线上免费接口签名服务超时(>8s)"
    except requests.exceptions.RequestException as e:
        return False, f"线上免费接口签名服务不可达:{e}"
    if resp.status_code != 200:
        return False, f"签名服务返回 HTTP {resp.status_code}"
    try:
        has_sign = bool(resp.json().get("sign"))
    except ValueError:
        return False, "签名服务响应非 JSON"
    return (True, "线上免费接口可达") if has_sign else (False, "签名服务未返回 sign")


def _probe_whisper(cfg: AsrConfig) -> Tuple[bool, str]:
    if not cfg.whisper_model_path:
        return False, "未配置 whisper 模型路径"
    if not os.path.exists(cfg.whisper_model_path):
        return False, f"模型文件不存在:{cfg.whisper_model_path}"
    return True, f"模型就绪:{cfg.whisper_model_path}"


def _probe_external(cfg: AsrConfig) -> Tuple[bool, str]:
    if not cfg.external_endpoint:
        return False, "未配置外部 ASR endpoint"
    headers = {"Authorization": f"Bearer {cfg.external_api_key}"} if cfg.external_api_key else {}
    try:
        resp = requests.get(cfg.external_endpoint, headers=headers, timeout=_PROBE_TIMEOUT)
    except requests.exceptions.Timeout:
        return False, "外部 endpoint 超时(>8s)"
    except requests.exceptions.RequestException as e:
        return False, f"外部 endpoint 不可达:{e}"
    # 连通即视为可达(外部服务健康路径各异,不强求 200)
    return True, f"外部 endpoint 可达(HTTP {resp.status_code})"
