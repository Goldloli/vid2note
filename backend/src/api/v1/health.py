"""``GET /api/v1/health`` —— 健康检查(契约 §4.1)。

返回外部工具(``yt-dlp`` / ``ffmpeg``)可执行性 + 当前引擎配置态,供前端引擎状态卡展示。
"""
import shutil

from fastapi import APIRouter

from src.runtime.settings import get_settings_snapshot
from src.runtime.task_service import get_task_service

router = APIRouter(prefix="/health", tags=["health"])


def _which(name: str) -> bool:
    """判断可执行文件是否在 PATH 中。"""
    return shutil.which(name) is not None


@router.get("")
async def health_check():
    """健康检查:工具可执行性 + 引擎配置态。"""
    repo = get_task_service().repo
    snapshot = get_settings_snapshot(repo)
    return {
        "status": "healthy",
        "service": "vid2note",
        "tools": {
            # 媒体下载与音频提取依赖 yt-dlp / ffmpeg(契约 §6.1)
            "yt-dlp": _which("yt-dlp") or _which("youtube-dl"),
            "ffmpeg": _which("ffmpeg"),
        },
        "engines": {
            # 引擎配置态(从 SQLite settings 读出的强类型快照)
            "asr_engine": snapshot.get("asr.engine"),
            "asr_strategy": snapshot.get("asr.strategy"),
            "llm_provider": snapshot.get("llm.provider"),
            "llm_model": snapshot.get("llm.model"),
            "pdf_mode": snapshot.get("pdf.mode"),
            "output_language": snapshot.get("note.output_language"),
        },
        "concurrency_max": int(snapshot.get("concurrency.max", "1") or 1),
    }
