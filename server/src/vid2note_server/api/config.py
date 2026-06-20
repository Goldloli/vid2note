"""配置 API

读写 AppConfig（yaml），API Key 走 ConfigManager（Keychain/env）。
不把任何密钥回传给前端。
"""

import logging

from fastapi import APIRouter, Response

from vid2note_server.dependencies import ServicesDependency
from vid2note_server.schemas.common import ERROR_RESPONSES
from vid2note_server.schemas.config import (
    ConfigResponse,
    ConfigUpdateResponse,
    StoreApiKeyRequest,
    UpdateConfigRequest,
    VerifyKeyRequest,
    VerifyKeyResponse,
)

router = APIRouter(tags=["config"], responses=ERROR_RESPONSES)
logger = logging.getLogger(__name__)


def _safe_config_dump(config) -> dict:
    """导出配置，但抹掉所有 api_key 字段（前端不应看到密钥）。"""
    data = config.model_dump()
    for prov_cfg in data.values():
        if isinstance(prov_cfg, dict):
            for k in list(prov_cfg.keys()):
                if "api_key" in k or "secret" in k:
                    prov_cfg[k] = "***" if prov_cfg[k] else ""
    return data


@router.get("/config", response_model=ConfigResponse)
async def get_config(services: ServicesDependency):
    """返回当前配置（脱敏，不含密钥）"""
    manager = services.config
    config = manager.load()
    return _safe_config_dump(config)


@router.put("/config", response_model=ConfigUpdateResponse)
async def update_config(req: UpdateConfigRequest, services: ServicesDependency):
    """更新配置（部分字段），持久化到 yaml"""
    manager = services.config
    config = manager.load()
    changed = []
    if req.autonomy_mode is not None:
        config.autonomy_mode = req.autonomy_mode
        changed.append("autonomy_mode")
    if req.llm_provider is not None:
        config.llm_provider = req.llm_provider
        changed.append("llm_provider")
    if req.asr_provider is not None and config.asr is not None:
        config.asr.provider = req.asr_provider
        changed.append("asr.provider")
    # 保留策略
    if req.keep_video is not None:
        config.retention.keep_video = req.keep_video
        changed.append("retention.keep_video")
    if req.keep_audio is not None:
        config.retention.keep_audio = req.keep_audio
        changed.append("retention.keep_audio")
    if req.keep_srt is not None:
        config.retention.keep_srt = req.keep_srt
        changed.append("retention.keep_srt")
    if req.keep_markdown is not None:
        config.retention.keep_markdown = req.keep_markdown
        changed.append("retention.keep_markdown")
    if req.keep_mindmap is not None:
        config.retention.keep_mindmap = req.keep_mindmap
        changed.append("retention.keep_mindmap")
    # 处理选项
    if req.language is not None:
        config.processing.language = req.language
        changed.append("processing.language")
    if req.mindmap_format is not None:
        config.processing.mindmap_format = req.mindmap_format
        changed.append("processing.mindmap_format")
    if req.vault_path is not None:
        config.workspace.vault_path = req.vault_path
        changed.append("workspace.vault_path")
    if req.default_runtime is not None:
        config.workspace.default_runtime = req.default_runtime
        changed.append("workspace.default_runtime")
    if req.clip_buffer_ms is not None:
        config.workspace.clip_buffer_ms = req.clip_buffer_ms
        changed.append("workspace.clip_buffer_ms")
    if changed:
        manager.save(config)
    return {"message": "配置已更新", "changed": changed}


@router.put("/config/api-key", status_code=204)
async def store_api_key(req: StoreApiKeyRequest, services: ServicesDependency):
    """Store one provider credential without returning or writing it to YAML."""
    services.config.set_api_key(req.provider, req.api_key)
    return Response(status_code=204)


@router.post("/config/verify", response_model=VerifyKeyResponse)
async def verify_api_key(req: VerifyKeyRequest):
    """校验 API Key 是否可用（对 LLM provider 做一次最小调用）"""
    from vid2note_core.llm.factory import LLMFactory

    try:
        llm = LLMFactory.create(req.provider, {"api_key": req.api_key, "model": "test"})
        llm.chat([{"role": "user", "content": "ping"}], max_tokens=1, timeout=10)
        return {"valid": True}
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "API key verification failed provider=%s error_type=%s",
            req.provider,
            type(exc).__name__,
        )
        return {"valid": False, "error": "API key verification failed"}
