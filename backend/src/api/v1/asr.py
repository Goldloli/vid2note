"""``GET/POST /api/v1/asr`` —— ASR 引擎状态与连通性测试(openspec change asr-management-page)。

- ``GET /asr/status``:三引擎就绪态(读 settings + 文件系统检查,无副作用,秒回)。
- ``POST /asr/test {engine}``:连通性测试——bcut 探活 / whisper 检查模型 / external
  探活 endpoint,统一返回 ``{ok, latency_ms, message}``。**不做真实音频转录**(v1 边界)。

端点用同步 ``def``(非 async):内部用同步 ``requests``,FastAPI 自动放线程池执行,不阻塞事件循环。
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Tuple
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.core.kernel import logger
from src.runtime.settings import get_external_asr_api_key, get_settings_snapshot
from src.runtime.task_service import get_task_service
from src.speech_to_text.pipeline import AsrConfig

router = APIRouter(prefix="/asr", tags=["asr"])

_ENGINES = frozenset({"bcut", "whisper_cpp", "external"})
_PROBE_TIMEOUT = 8.0
_BCUT_PROBE_URL = "https://member.bilibili.com"


class AsrTestRequest(BaseModel):
    engine: str


def _asr_config() -> AsrConfig:
    """从文件设置与加密凭证构造当前 ASR 配置。"""
    repo = get_task_service().repo
    config = AsrConfig.from_settings(get_settings_snapshot(repo))
    config.external_api_key = get_external_asr_api_key()
    return config


@router.get("/status")
def asr_status() -> Dict[str, Any]:
    """三引擎就绪态(无副作用)。"""
    cfg = _asr_config()
    model_exists = bool(cfg.whisper_model_path) and os.path.exists(cfg.whisper_model_path)
    binary_exists = bool(cfg.whisper_binary) and os.path.exists(cfg.whisper_binary)
    endpoint_configured = bool(cfg.external_endpoint)
    endpoint_host = urlparse(cfg.external_endpoint).hostname or ""
    return {
        "selection": {
            "engine": cfg.engine,
            "strategy": cfg.strategy,
        },
        "bcut": {
            "available": True,  # 在线引擎恒可用,实际可达性由 /test 探活
            "experimental": True,
            "timeout": cfg.bcut_timeout,
        },
        "whisper_cpp": {
            "available": model_exists,
            "model_exists": model_exists,
            "model_path": cfg.whisper_model_path,
            "binary_exists": binary_exists,
            "binary_path": cfg.whisper_binary,
            "language": cfg.whisper_language,
            "device": cfg.whisper_device,
            "compute_type": cfg.whisper_compute_type,
        },
        "external": {
            "available": endpoint_configured,
            "endpoint_configured": endpoint_configured,
            "endpoint_host": endpoint_host,
            "api_key_configured": bool(cfg.external_api_key),
            "timeout": cfg.external_timeout,
        },
        "vad": {
            "threshold_seconds": cfg.vad_threshold_seconds,
            "target_segment_seconds": cfg.vad_target_segment_seconds,
            "concurrency": cfg.concurrency,
            "request_timeout": cfg.request_timeout,
        },
    }


@router.post("/test")
def asr_test(req: AsrTestRequest) -> Dict[str, Any]:
    """连通性测试(非真实转录):探活 / 模型可加载,返回 {ok, latency_ms, message}。"""
    engine = (req.engine or "").strip().lower()
    if engine not in _ENGINES:
        raise HTTPException(status_code=400, detail=f"不支持的引擎:{engine}(允许 bcut/whisper_cpp/external)")
    cfg = _asr_config()
    start = time.perf_counter()
    try:
        if engine == "bcut":
            ok, msg = _probe_bcut()
        elif engine == "whisper_cpp":
            ok, msg = _probe_whisper(cfg)
        else:
            ok, msg = _probe_external(cfg)
    except Exception:  # noqa: BLE001 - 探活任何异常都转为失败结果,不抛 500
        logger.exception("ASR 连通性测试异常 engine=%s", engine)
        ok, msg = False, "连通性测试失败，请查看服务端日志"
    return {
        "engine": engine,
        "ok": ok,
        "latency_ms": int((time.perf_counter() - start) * 1000),
        "message": msg,
    }


def _probe_bcut() -> Tuple[bool, str]:
    """不上传音频的 bcut 轻量探活。"""
    try:
        resp = requests.get(
            _BCUT_PROBE_URL,
            timeout=_PROBE_TIMEOUT,
            allow_redirects=False,
        )
    except requests.exceptions.Timeout:
        return False, "bcut 超时(>8s)"
    except requests.exceptions.RequestException:
        logger.warning("bcut 探活失败", exc_info=True)
        return False, "bcut 不可达"
    return (
        (True, "bcut 可达")
        if resp.status_code < 500
        else (False, f"bcut 返回 HTTP {resp.status_code}")
    )


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
    except requests.exceptions.RequestException:
        logger.warning("外部 ASR endpoint 探活失败", exc_info=True)
        return False, "外部 endpoint 不可达"
    # 连通即视为可达(外部服务健康路径各异,不强求 200)
    return True, f"外部 endpoint 可达(HTTP {resp.status_code})"
