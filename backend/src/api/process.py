"""
任务处理接口
"""
import os
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..core import get_task_queue
from ..models.task import TaskStatus
from ..utils.rate_limiter import limiter
from ..utils.security import is_safe_path


router = APIRouter(prefix="/api/v1/process", tags=["process"])

# 输出目录 - 支持环境变量覆盖（容器化部署），否则使用项目本地目录
_DEFAULT_OUTPUT = Path(__file__).parent.parent.parent.parent / "output"
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", str(_DEFAULT_OUTPUT)))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class ProcessRequest(BaseModel):
    """处理请求"""
    task_id: str
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    extract_images: bool = False
    image_quality: str = "medium"
    export_mindmap: bool = False
    mindmap_format: str = "xmind"  # xmind 或 png


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: str
    status: str
    progress: int = Field(0, ge=0, le=100)
    current_step: Optional[str] = None
    message: Optional[str] = None
    download_url: Optional[str] = None
    mindmap_url: Optional[str] = None


@router.post("/start")
@limiter.limit("5/minute")  # 每IP每分钟5次任务启动
async def start_processing(request: Request, process_request: ProcessRequest):
    """
    开始处理任务

    任务会进入队列等待后台工作器处理
    """
    task_queue = get_task_queue()
    task = task_queue.get_task_status(process_request.task_id)

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 检查任务状态
    if task.status == TaskStatus.PROCESSING:
        raise HTTPException(status_code=400, detail="任务正在处理中")

    if task.status == TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="任务已完成")

    # 更新任务的 LLM 配置和处理选项
    update_data = {}
    if process_request.llm_provider:
        update_data['llm_provider'] = process_request.llm_provider
    if process_request.llm_model:
        update_data['llm_model'] = process_request.llm_model
    if process_request.export_mindmap is not None:
        update_data['export_mindmap'] = process_request.export_mindmap
    if process_request.mindmap_format:
        update_data['mindmap_format'] = process_request.mindmap_format

    if update_data:
        task_queue.repository.update(process_request.task_id, **update_data)

    # 确保工作器已启动
    from ..core import start_worker
    import asyncio
    asyncio.create_task(start_worker())

    return {
        'task_id': process_request.task_id,
        'status': TaskStatus.PENDING.value,
        'message': '任务已加入队列，将在后台处理'
    }


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_status(task_id: str):
    """
    查询任务状态

    从数据库获取最新状态，支持页面刷新后查询
    """
    task_queue = get_task_queue()
    task = task_queue.get_task_status(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return TaskStatusResponse(
        task_id=task.id,
        status=task.status.value,
        progress=task.progress,
        current_step=task.current_step,
        message=task.message,
        download_url=task.download_url,
        mindmap_url=task.mindmap_url
    )


@router.get("/{task_id}/download")
async def download_result(task_id: str):
    """
    下载处理结果（Markdown文件）
    """
    from fastapi.responses import FileResponse

    task_queue = get_task_queue()
    task = task_queue.get_task_status(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status != TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="任务尚未完成")

    # 获取原始文件名用于下载名称（优先SRT，其次TXT）
    if task.srt_original_name:
        download_name = f"{Path(task.srt_original_name).stem}.md"
    elif task.txt_original_name:
        download_name = f"{Path(task.txt_original_name).stem}.md"
    else:
        download_name = f"{task_id}.md"

    # 查找输出文件
    if task.output_file and Path(task.output_file).exists():
        output_file = Path(task.output_file)
    else:
        # 尝试在输出目录中查找
        output_file = OUTPUT_DIR / download_name
        if not output_file.exists():
            output_file = OUTPUT_DIR / f"{task_id}.md"

    # 验证路径安全 - 确保在输出目录内（防止路径遍历攻击）
    if not is_safe_path(OUTPUT_DIR, output_file):
        raise HTTPException(
            status_code=400,
            detail="无效的文件路径"
        )

    if not output_file.exists():
        raise HTTPException(status_code=404, detail="结果文件不存在")

    return FileResponse(
        path=str(output_file),
        filename=download_name,
        media_type="text/markdown"
    )


@router.get("/{task_id}/download/mindmap")
async def download_mindmap(task_id: str):
    """
    下载思维导图文件（XMind格式）
    """
    from fastapi.responses import FileResponse

    task_queue = get_task_queue()
    task = task_queue.get_task_status(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status != TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="任务尚未完成")

    if not task.mindmap_file:
        raise HTTPException(status_code=404, detail="思维导图未生成")

    # 确定文件扩展名
    mindmap_path = Path(task.mindmap_file)
    file_ext = mindmap_path.suffix.lower()

    # 获取原始文件名用于下载名称
    if task.srt_original_name:
        base_name = Path(task.srt_original_name).stem
    elif task.txt_original_name:
        base_name = Path(task.txt_original_name).stem
    else:
        base_name = task_id

    # 根据实际文件类型设置下载名称和MIME类型
    if file_ext == '.xmind':
        download_name = f"{base_name}.xmind"
        media_type = "application/vnd.xmind.workbook"
    elif file_ext == '.png':
        download_name = f"{base_name}_mindmap.png"
        media_type = "image/png"
    elif file_ext == '.txt':
        download_name = f"{base_name}_outline.txt"
        media_type = "text/plain"
    else:
        # Fallback to old .mmd format for compatibility
        download_name = f"{base_name}.mmd"
        media_type = "text/plain"

    # 查找思维导图文件
    if mindmap_path.exists():
        mindmap_file = mindmap_path
    else:
        # 尝试在输出目录中查找（支持多种格式）
        for ext in ['.xmind', '.png', '.txt', '.mmd']:
            mindmap_file = OUTPUT_DIR / f"{base_name}{ext}"
            if mindmap_file.exists():
                # 更新下载名称以匹配找到的文件
                if ext == '.xmind':
                    download_name = f"{base_name}.xmind"
                    media_type = "application/vnd.xmind.workbook"
                elif ext == '.png':
                    download_name = f"{base_name}_mindmap.png"
                    media_type = "image/png"
                else:
                    download_name = f"{base_name}_outline{ext}"
                    media_type = "text/plain"
                break
        else:
            raise HTTPException(status_code=404, detail="思维导图文件不存在")

    # 验证路径安全 - 确保在输出目录内（防止路径遍历攻击）
    if not is_safe_path(OUTPUT_DIR, mindmap_file):
        raise HTTPException(
            status_code=400,
            detail="无效的文件路径"
        )

    return FileResponse(
        path=str(mindmap_file),
        filename=download_name,
        media_type=media_type
    )
