"""上传 API"""
from fastapi import APIRouter

router = APIRouter(tags=["upload"])

@router.post("/upload/srt")
async def upload_srt():
    return {"file_id": "file_xxx"}

@router.post("/upload/pdf")
async def upload_pdf():
    return {"file_id": "file_xxx"}

@router.post("/upload/txt")
async def upload_txt():
    return {"file_id": "file_xxx"}
