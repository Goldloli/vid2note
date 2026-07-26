"""
文件上传接口
"""
import re
import uuid
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from pydantic import BaseModel

from ..core import get_task_queue
from ..core.task_queue import QueueFullError
from ..config import config_manager
from ..utils.rate_limiter import limiter


router = APIRouter(prefix="/api/v1/upload", tags=["upload"])

# 上传目录（从配置文件读取）
config = config_manager.load()
UPLOAD_DIR = Path(config.server.temp_dir) / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 允许的文件类型
ALLOWED_SRT_TYPES = {'.srt'}
ALLOWED_TXT_TYPES = {'.txt'}
ALLOWED_PDF_TYPES = {'.pdf'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# file_id 格式验证正则表达式
FILE_ID_PATTERN = re.compile(r'^file_[a-f0-9]{12}$')
TASK_ID_PATTERN = re.compile(r'^task_[a-f0-9]{12}$')


class UploadResponse(BaseModel):
    """上传响应"""
    file_id: str
    filename: str
    file_type: str
    size: int
    message: str


class TaskFiles(BaseModel):
    """任务文件信息"""
    task_id: str
    srt_file: Optional[str] = None
    pdf_file: Optional[str] = None


# 存储任务文件映射（实际应用中应使用Redis或数据库）
task_files: dict = {}

# 存储 file_id 到原始文件名的映射
file_id_to_name: dict = {}


def generate_file_id() -> str:
    """生成文件ID"""
    return f"file_{uuid.uuid4().hex[:12]}"


def generate_task_id() -> str:
    """生成任务ID"""
    return f"task_{uuid.uuid4().hex[:12]}"


def validate_file_id(file_id: str) -> bool:
    """
    验证 file_id 格式，防止路径遍历攻击
    
    有效的 file_id 格式: file_xxxxxxxxxxxx (12位十六进制)
    """
    if not file_id:
        return False
    return bool(FILE_ID_PATTERN.match(file_id))


def validate_task_id(task_id: str) -> bool:
    """
    验证 task_id 格式
    
    有效的 task_id 格式: task_xxxxxxxxxxxx (12位十六进制)
    """
    if not task_id:
        return False
    return bool(TASK_ID_PATTERN.match(task_id))


def validate_file(file: UploadFile, allowed_types: set) -> tuple:
    """验证文件类型和大小"""
    # 检查文件名
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    
    # 检查文件扩展名
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {ext}，支持的类型: {allowed_types}"
        )
    
    return ext


@router.post("/srt", response_model=UploadResponse)
@limiter.limit("10/minute")  # 每IP每分钟10次上传
async def upload_srt(request: Request, file: UploadFile = File(...)):
    """
    上传 SRT 字幕文件
    """
    ext = validate_file(file, ALLOWED_SRT_TYPES)
    
    # 读取文件内容
    content = await file.read()
    
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件大小超过限制（最大50MB）")
    
    # 保存文件
    file_id = generate_file_id()
    file_path = UPLOAD_DIR / f"{file_id}.srt"
    
    with open(file_path, 'wb') as f:
        f.write(content)

    # 保存 file_id 到原始文件名的映射
    file_id_to_name[file_id] = file.filename

    return UploadResponse(
        file_id=file_id,
        filename=file.filename,
        file_type="srt",
        size=len(content),
        message="SRT文件上传成功"
    )


@router.post("/pdf", response_model=UploadResponse)
@limiter.limit("10/minute")  # 每IP每分钟10次上传
async def upload_pdf(request: Request, file: UploadFile = File(...)):
    """
    上传 PDF 课件文件
    """
    ext = validate_file(file, ALLOWED_PDF_TYPES)

    # 读取文件内容
    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件大小超过限制（最大50MB）")

    # 保存文件
    file_id = generate_file_id()
    file_path = UPLOAD_DIR / f"{file_id}.pdf"

    with open(file_path, 'wb') as f:
        f.write(content)

    # 保存 file_id 到原始文件名的映射
    file_id_to_name[file_id] = file.filename

    return UploadResponse(
        file_id=file_id,
        filename=file.filename,
        file_type="pdf",
        size=len(content),
        message="PDF文件上传成功"
    )


@router.post("/txt", response_model=UploadResponse)
@limiter.limit("10/minute")  # 每IP每分钟10次上传
async def upload_txt(request: Request, file: UploadFile = File(...)):
    """
    上传 TXT 文本文件
    """
    ext = validate_file(file, ALLOWED_TXT_TYPES)

    # 读取文件内容
    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件大小超过限制（最大50MB）")

    # 保存文件
    file_id = generate_file_id()
    file_path = UPLOAD_DIR / f"{file_id}.txt"

    with open(file_path, 'wb') as f:
        f.write(content)

    # 保存 file_id 到原始文件名的映射
    file_id_to_name[file_id] = file.filename

    return UploadResponse(
        file_id=file_id,
        filename=file.filename,
        file_type="txt",
        size=len(content),
        message="TXT文件上传成功"
    )


@router.post("/task", response_model=dict)
async def create_task(
    srt_file_id: Optional[str] = None,
    txt_file_id: Optional[str] = None,
    pdf_file_id: Optional[str] = None
):
    """
    创建处理任务
    支持 SRT、TXT 作为内容源，PDF 作为可选的章节参考
    """
    # 至少需要 SRT 或 TXT 之一
    if not srt_file_id and not txt_file_id:
        raise HTTPException(status_code=400, detail="至少需要上传一个字幕文件(SRT)或文本文件(TXT)")

    # 验证 file_id 格式，防止路径遍历攻击
    if srt_file_id and not validate_file_id(srt_file_id):
        raise HTTPException(status_code=400, detail="无效的SRT文件ID格式")
    if txt_file_id and not validate_file_id(txt_file_id):
        raise HTTPException(status_code=400, detail="无效的TXT文件ID格式")
    if pdf_file_id and not validate_file_id(pdf_file_id):
        raise HTTPException(status_code=400, detail="无效的PDF文件ID格式")

    task_id = generate_task_id()

    # 验证文件是否存在
    srt_path = None
    txt_path = None
    pdf_path = None

    if srt_file_id:
        srt_path = UPLOAD_DIR / f"{srt_file_id}.srt"
        if not srt_path.exists():
            raise HTTPException(status_code=404, detail="SRT文件不存在")

    if txt_file_id:
        txt_path = UPLOAD_DIR / f"{txt_file_id}.txt"
        if not txt_path.exists():
            raise HTTPException(status_code=404, detail="TXT文件不存在")

    if pdf_file_id:
        pdf_path = UPLOAD_DIR / f"{pdf_file_id}.pdf"
        if not pdf_path.exists():
            raise HTTPException(status_code=404, detail="PDF文件不存在")

    # 从 file_id_to_name 映射中获取原始文件名
    srt_original_name = file_id_to_name.get(srt_file_id) if srt_file_id else None
    txt_original_name = file_id_to_name.get(txt_file_id) if txt_file_id else None
    pdf_original_name = file_id_to_name.get(pdf_file_id) if pdf_file_id else None

    # 保存到内存映射（供旧代码兼容）
    task_files[task_id] = {
        'srt_file': str(srt_path) if srt_path else None,
        'txt_file': str(txt_path) if txt_path else None,
        'pdf_file': str(pdf_path) if pdf_path else None,
        'srt_original_name': srt_original_name,
        'txt_original_name': txt_original_name,
        'pdf_original_name': pdf_original_name,
        'status': 'pending'
    }

    # 创建数据库任务（队列持久化）
    task_queue = get_task_queue()

    # 检查队列是否已满
    if task_queue.is_queue_full():
        queue_status = task_queue.get_queue_status()
        raise HTTPException(
            status_code=429,
            detail=f"队列已满，当前活跃任务: {queue_status['active_count']}/{queue_status['max_queue_size']}，请稍后重试"
        )

    try:
        task = task_queue.submit_task(
            task_id=task_id,
            srt_file=str(srt_path) if srt_path else None,
            txt_file=str(txt_path) if txt_path else None,
            pdf_file=str(pdf_path) if pdf_path else None,
            srt_original_name=srt_original_name,
            txt_original_name=txt_original_name,
            pdf_original_name=pdf_original_name
        )
    except QueueFullError as e:
        raise HTTPException(status_code=429, detail=str(e))

    return {
        'task_id': task_id,
        'status': task.status.value,
        'message': '任务创建成功，请调用处理接口开始处理'
    }
