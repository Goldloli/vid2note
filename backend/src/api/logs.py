"""
日志管理接口
接收前端日志并统一管理
"""
from typing import List, Optional, Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
from pathlib import Path

from ..utils.logger import logger, task_log, LOG_DIR

router = APIRouter(prefix="/api/v1/logs", tags=["logs"])


class FrontendLogEntry(BaseModel):
    """前端日志条目"""
    level: Literal["debug", "info", "warning", "error"]
    message: str
    timestamp: Optional[str] = None
    component: Optional[str] = None
    task_id: Optional[str] = None
    extra: Optional[dict] = None


class LogQueryParams(BaseModel):
    """日志查询参数"""
    level: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    task_id: Optional[str] = None
    limit: int = 100


def get_frontend_log_file() -> Path:
    """获取前端日志文件路径"""
    today = datetime.now().strftime("%Y-%m-%d")
    return LOG_DIR / f"frontend-{today}.log"


def format_frontend_log(entry: FrontendLogEntry) -> str:
    """格式化前端日志"""
    timestamp = entry.timestamp or datetime.now().isoformat()
    level = entry.level.upper()
    component = f"[{entry.component}]" if entry.component else ""
    task = f"[task={entry.task_id}]" if entry.task_id else ""

    log_line = f"[{timestamp}] [{level}]{component}{task} {entry.message}"

    if entry.extra:
        import json
        log_line += f" | extra: {json.dumps(entry.extra, ensure_ascii=False)}"

    return log_line


@router.post("/frontend")
async def receive_frontend_logs(logs: List[FrontendLogEntry]):
    """
    接收前端日志
    """
    try:
        log_file = get_frontend_log_file()

        with open(log_file, "a", encoding="utf-8") as f:
            for entry in logs:
                log_line = format_frontend_log(entry)
                f.write(log_line + "\n")

                # 同时输出到后端日志
                if entry.task_id:
                    task_log(entry.task_id, f"[Frontend] {entry.message}", entry.level)
                else:
                    getattr(logger, entry.level)(f"[Frontend] {entry.message}")

        return {"success": True, "count": len(logs)}

    except Exception as e:
        logger.error(f"保存前端日志失败: {e}")
        raise HTTPException(status_code=500, detail=f"保存日志失败: {str(e)}")


@router.get("/backend")
async def get_backend_logs(
    level: Optional[str] = None,
    task_id: Optional[str] = None,
    lines: int = 100
):
    """
    获取后端日志
    """
    try:
        from ..utils.logger import get_log_file

        log_file = get_log_file()

        if not log_file.exists():
            return {"logs": [], "total": 0}

        # 读取最后 N 行
        with open(log_file, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        # 过滤
        filtered = all_lines
        if level:
            filtered = [l for l in filtered if f"[{level.upper()}]" in l]
        if task_id:
            filtered = [l for l in filtered if f"task={task_id}" in l]

        # 返回最后 N 行
        result = filtered[-lines:] if len(filtered) > lines else filtered

        return {
            "logs": result,
            "total": len(result),
            "file": str(log_file)
        }

    except Exception as e:
        logger.error(f"读取后端日志失败: {e}")
        raise HTTPException(status_code=500, detail=f"读取日志失败: {str(e)}")


@router.get("/files")
async def list_log_files():
    """
    列出所有日志文件
    """
    try:
        files = []
        for log_file in LOG_DIR.glob("*.log"):
            stat = log_file.stat()
            files.append({
                "name": log_file.name,
                "path": str(log_file),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })

        files.sort(key=lambda x: x["modified"], reverse=True)

        return {"files": files}

    except Exception as e:
        logger.error(f"列出日志文件失败: {e}")
        raise HTTPException(status_code=500, detail=f"列出日志失败: {str(e)}")


@router.get("/frontend")
async def get_frontend_logs(lines: int = 100):
    """
    获取前端日志
    """
    try:
        log_file = get_frontend_log_file()

        if not log_file.exists():
            return {"logs": [], "total": 0}

        with open(log_file, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        result = all_lines[-lines:] if len(all_lines) > lines else all_lines

        return {
            "logs": result,
            "total": len(result),
            "file": str(log_file)
        }

    except Exception as e:
        logger.error(f"读取前端日志失败: {e}")
        raise HTTPException(status_code=500, detail=f"读取日志失败: {str(e)}")
