"""产物下载/导出 API

提供：
  - GET  /tasks/{id}/artifacts        列出任务所有产物
  - GET  /tasks/{id}/artifacts/{key}  下载单个产物（正确 Content-Type）
  - GET  /tasks/{id}/export           一键打包所有产物为 zip
"""

import zipfile
from io import BytesIO

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from vid2note_core.storage.artifact_store import ArtifactStore
from vid2note_core.storage.task_repo import TaskRepository
from vid2note_core.types import TaskId

router = APIRouter(tags=["artifacts"])

# artifact 键名 → (下载文件名, Content-Type, 友好类型)
# 键名来自 ArtifactStore 的 f"{node}_{name}" 命名约定
_ARTIFACT_META = {
    "transcribe_srt_file": ("transcript.srt", "application/x-subrip", "srt"),
    "organize_markdown_file": ("note.md", "text/markdown; charset=utf-8", "markdown"),
    "mindmap_mindmap_file": ("mindmap.mmd", "text/plain; charset=utf-8", "mindmap"),
    "cleanup_cleanup_manifest": ("cleanup.json", "application/json", "manifest"),
}


def _validate_task(task_id: str):
    """校验 task_id 格式与存在性，返回 TaskRepository。"""
    if not TaskId.is_valid(task_id):
        raise HTTPException(404, "任务不存在")
    repo = TaskRepository()
    if not repo.get_by_id(task_id):
        raise HTTPException(404, "任务不存在")
    return repo


@router.get("/tasks/{task_id}/artifacts")
async def list_artifacts(task_id: str):
    """列出任务的所有产物文件（名称、类型、大小）。"""
    _validate_task(task_id)
    store = ArtifactStore()
    items = []
    for path in store.list_artifacts(task_id):
        meta = _ARTIFACT_META.get(path.name)
        items.append(
            {
                "key": path.name,
                "name": meta[0] if meta else path.name,
                "content_type": meta[1] if meta else "application/octet-stream",
                "type": meta[2] if meta else "unknown",
                "size": path.stat().st_size,
            }
        )
    return {"task_id": task_id, "artifacts": items}


@router.get("/tasks/{task_id}/artifacts/{key}")
async def download_artifact(task_id: str, key: str):
    """下载单个产物文件（返回原始字节 + 正确 Content-Type + 附件下载头）。"""
    _validate_task(task_id)
    store = ArtifactStore()
    path = store._task_dir(task_id) / "artifacts" / key
    if not path.exists():
        raise HTTPException(404, "产物不存在")

    data = path.read_bytes()
    meta = _ARTIFACT_META.get(key)
    filename = meta[0] if meta else key
    content_type = meta[1] if meta else "application/octet-stream"

    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/tasks/{task_id}/export")
async def export_all_artifacts(task_id: str):
    """把任务所有产物打包为 zip 下载。"""
    _validate_task(task_id)
    store = ArtifactStore()
    files = store.list_artifacts(task_id)
    if not files:
        raise HTTPException(404, "任务暂无产物")

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            meta = _ARTIFACT_META.get(path.name)
            arcname = meta[0] if meta else path.name
            zf.writestr(arcname, path.read_bytes())
    buf.seek(0)

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="vid2note-{task_id}.zip"'},
    )
