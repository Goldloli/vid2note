"""上传 API

接收 SRT/PDF/TXT 文件，安全存储到 UploadStore，返回真实 file_id。
file_id 可在创建任务时引用（task_repo 的 srt_file/pdf_file/txt_file 字段）。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile

from vid2note_server.dependencies import Services, ServicesDependency
from vid2note_server.schemas.common import ERROR_RESPONSES
from vid2note_server.schemas.upload import UploadResponse

router = APIRouter(tags=["upload"], responses=ERROR_RESPONSES)

# 各类型允许的扩展名与最大字节数
_ALLOWED = {
    "srt": {".srt"},
    "pdf": {".pdf"},
    "txt": {".txt"},
}
MAX_SIZE = 50 * 1024 * 1024  # 50 MB


def _validate_and_store(upload: UploadFile, kind: str, services: Services) -> UploadResponse:
    """通用上传处理：校验扩展名/大小 → 存储 → 返回响应。"""
    filename = upload.filename or ""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED[kind]:
        raise HTTPException(
            400,
            f"不支持的文件类型: {ext or '(无扩展名)'}，{kind} 仅支持 {_ALLOWED[kind]}",
        )

    data = upload.file.read()
    if not data:
        raise HTTPException(400, "文件为空")
    if len(data) > MAX_SIZE:
        raise HTTPException(413, f"文件过大（>{MAX_SIZE // 1024 // 1024}MB）")

    store = services.uploads
    file_id = store.generate_file_id()
    store.save(file_id, filename, data)
    return UploadResponse(file_id=file_id, filename=filename, size=len(data))


@router.post("/upload/srt", response_model=UploadResponse)
async def upload_srt(file: UploadFile, services: ServicesDependency):
    return _validate_and_store(file, "srt", services)


@router.post("/upload/pdf", response_model=UploadResponse)
async def upload_pdf(file: UploadFile, services: ServicesDependency):
    return _validate_and_store(file, "pdf", services)


@router.post("/upload/txt", response_model=UploadResponse)
async def upload_txt(file: UploadFile, services: ServicesDependency):
    return _validate_and_store(file, "txt", services)
