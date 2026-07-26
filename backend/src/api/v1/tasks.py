"""``/api/v1/tasks`` —— 任务路由(契约 §4.1)。

端点:
- ``POST /tasks``                 创建任务(source_url 或 multipart 文件 + 引擎选项 + 可选 PDF)
- ``GET /tasks``                  历史列表(筛选 status / source_type / q + 分页)
- ``POST /tasks/batch``           批量导出(zip)/ 批量重跑
- ``GET /tasks/{id}``             任务详情
- ``GET /tasks/{id}/stream``      SSE 实时进度 / 日志
- ``POST /tasks/{id}/rerun``      节点级重跑(?from=<node>)
- ``POST /tasks/{id}/cancel``     取消任务
- ``GET /tasks/{id}/products/{kind}``  下载产物(防越界)
"""
from __future__ import annotations

import json
import mimetypes
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, Form, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse

from src.media_ingest import UploadedFile
from src.models.task import TASK_STATUSES, TERMINAL_TASK_STATUSES
from src.runtime.settings import clamp_concurrency, get_settings_snapshot
from src.runtime.task_service import get_task_service
from src.sse import get_bus
from src.utils.security import is_safe_path, secure_filename

router = APIRouter(prefix="/tasks", tags=["tasks"])


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #
def _to_bool(value: Any) -> Optional[bool]:
    """表单字符串 → 布尔;空 → None(交由 settings 默认)。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s == "":
        return None
    return s in ("1", "true", "yes", "on")


def _queue_full(repo: Any, snapshot: Dict[str, str]) -> bool:
    """判断任务队列是否已满(契约 §4.1:队列满 → 429)。

    队列容量 = 并发槽数 × 2(每个并发槽允许 1 个 FIFO 积压,个人本地工具避免无限堆积)。
    活跃任务 = pending + running。
    """
    cap = max(1, clamp_concurrency(snapshot.get("concurrency.max", "1"))) * 2
    try:
        active = repo.count_active()
    except Exception:  # noqa: BLE001 - 读库失败不阻断创建(回落为不满)
        return False
    return active >= cap


def _persist_upload(upload: UploadFile, data_root: Path, subdir: str) -> tuple[str, str, str, int]:
    """把上传文件落到 ``data_root/temp/<subdir>/`` 暂存,返回
    (abs_path, original_name, mime, size_bytes)。"""
    original = secure_filename(upload.filename or "upload")
    staging_dir = data_root / "temp" / subdir
    staging_dir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:8]
    dst = staging_dir / f"{token}_{original}"
    size = 0
    with dst.open("wb") as fp:
        while True:
            chunk = upload.file.read(1 << 20)
            if not chunk:
                break
            fp.write(chunk)
            size += len(chunk)
    return str(dst), upload.filename or original, upload.content_type or "", size


def _persist_pdf_upload(upload: UploadFile, data_root: Path) -> str:
    """把用户附带的 PDF 落到 ``data_root/pdf/_pending/``,返回相对 DATA_ROOT 的路径。

    PDF 是**输入**(非五类产物),独立于 task_id 暂存,避免与任务创建竞态;
    不在 retention 五类产物目录中,故不会被清理扫描回收。
    """
    original = secure_filename(upload.filename or "lecture.pdf")
    if not original.lower().endswith(".pdf"):
        original = f"{original}.pdf"
    pending_dir = data_root / "pdf" / "_pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:8]
    dst = pending_dir / f"{token}_{original}"
    with dst.open("wb") as fp:
        while True:
            chunk = upload.file.read(1 << 20)
            if not chunk:
                break
            fp.write(chunk)
    return dst.relative_to(data_root).as_posix()


def _sse(payload: Dict[str, Any]) -> str:
    """格式化一条 SSE 事件(data-only)。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _stream_events(task_id: str) -> AsyncIterator[str]:
    """SSE 流:先推权威态快照(从库读),已终态则推终态事件后关闭,否则续推实时事件。"""
    bus = get_bus()
    svc = get_task_service()
    task = svc.get_task(task_id)
    if task is None:
        yield _sse({"task_id": task_id, "event": "task-missing", "payload": {"error": "任务不存在"}})
        return

    status = task.status.value if hasattr(task.status, "value") else str(task.status)
    snapshot_payload = {
        "status": status,
        "progress": task.progress,
        "node_statuses": dict(task.node_statuses or {}),
        "error": task.error,
    }
    yield _sse({"task_id": task_id, "event": "snapshot", "payload": snapshot_payload})

    # 已终态:推对应终态事件后正常关闭(契约 §6.8)
    if status in TERMINAL_TASK_STATUSES:
        terminal = {
            "completed": "task-completed",
            "failed": "task-failed",
            "cancelled": "task-cancelled",
        }.get(status, "task-completed")
        yield _sse({"task_id": task_id, "event": terminal, "payload": snapshot_payload})
        return

    # 活跃任务:订阅总线,续推实时事件直到终态(契约 §6.8 / bus.stream)
    async for chunk in bus.stream(task_id, None):
        yield chunk


def _resolve_product_rel(task: Any, kind: str, index: int) -> Optional[str]:
    """根据 kind 解析产物相对路径;标量类直接取,列表类按 index 取。"""
    if kind == "pdf":
        # PDF 讲义是用户上传的输入(非流水线产物),供笔记页双栏对照取阅
        return task.pdf_path
    if kind == "note":
        return task.note_path
    if kind == "srt":
        return task.srt_path
    if kind == "video":
        return task.video_path
    if kind == "audio":
        return task.audio_path
    if kind == "mindmap":
        paths = list(task.mindmap_paths or [])
        if 0 <= index < len(paths):
            return paths[index]
        return None
    if kind == "screenshot":
        paths = list(task.screenshot_paths or [])
        if 0 <= index < len(paths):
            return paths[index]
        return None
    return None


# --------------------------------------------------------------------------- #
# 创建任务
# --------------------------------------------------------------------------- #
@router.post("", status_code=201)
async def create_task(
    source_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    pdf: Optional[UploadFile] = File(None),
    title: Optional[str] = Form(None),
    asr_engine: Optional[str] = Form(None),
    llm_provider: Optional[str] = Form(None),
    llm_model: Optional[str] = Form(None),
    pdf_mode: Optional[str] = Form(None),
    extract_images: Optional[str] = Form(None),
    output_language: Optional[str] = Form(None),
    mindmap_formats: Optional[List[str]] = Form(None),
):
    """创建任务(契约 §4.1 ``POST /tasks``)。

    接受 ``source_url`` 或本地文件(二选一)+ 引擎选项 + 可选 PDF;
    队列满 → 429;无法识别媒体来源 → 400(中文)。
    """
    svc = get_task_service()
    repo = svc.repo
    snapshot = get_settings_snapshot(repo)

    # 队列满检查(创建前)
    if _queue_full(repo, snapshot):
        raise HTTPException(
            status_code=429,
            detail="任务队列已满,请等待现有任务结束后再提交",
        )

    # 暂存上传文件(media + PDF)
    uploaded: Optional[UploadedFile] = None
    pdf_rel: Optional[str] = None
    if pdf is not None and pdf.filename:
        try:
            pdf_rel = _persist_pdf_upload(pdf, svc.data_root)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"PDF 保存失败:{exc}")

    if file is not None and file.filename:
        try:
            abs_path, original, mime, size = _persist_upload(file, svc.data_root, "_staging")
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"上传文件保存失败:{exc}")
        uploaded = UploadedFile(
            abs_path=abs_path, original_name=original, mime=mime, size_bytes=size
        )

    # 创建任务(无法识别来源抛 ValueError)
    try:
        task = svc.create_task(
            source_url=source_url,
            uploaded=uploaded,
            title=title,
            llm_provider=llm_provider,
            llm_model=llm_model,
            asr_engine=asr_engine,
            pdf_mode=pdf_mode,
            extract_images=_to_bool(extract_images),
            output_language=output_language,
            mindmap_formats=mindmap_formats,
            pdf_path=pdf_rel,
        )
    except ValueError as exc:
        # 无法识别媒体来源(契约 §4.1 → 400)
        raise HTTPException(status_code=400, detail=str(exc) or "无法识别的媒体来源")

    return task.to_dict()


# --------------------------------------------------------------------------- #
# 历史列表
# --------------------------------------------------------------------------- #
@router.get("")
async def list_tasks(
    status: Optional[str] = Query(None, description="按状态筛选"),
    source_type: Optional[str] = Query(None, description="按来源类型筛选"),
    q: Optional[str] = Query(None, description="关键词(标题/链接/来源,大小写不敏感)"),
    page: int = Query(1, ge=1, description="页码(1-based)"),
    page_size: int = Query(20, ge=1, le=200, description="每页条数"),
):
    """任务历史(契约 §4.1 ``GET /tasks``)。"""
    if status is not None and status != "" and status not in TASK_STATUSES:
        raise HTTPException(status_code=400, detail=f"非法状态:{status}")
    result = get_task_service().list_history(
        status=status or None,
        source_type=source_type or None,
        q=q or None,
        page=page,
        page_size=page_size,
    )
    return {
        "items": [t.to_dict() for t in result["items"]],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
    }


# --------------------------------------------------------------------------- #
# 批量
# --------------------------------------------------------------------------- #
class _BatchBody:
    """(轻量解析)``{"action":"export"|"rerun","task_ids":[...]}``"""


@router.get("/stats")
async def task_stats():
    """运行态聚合统计(openspec change console-history-detail-nav)。"""
    return get_task_service().aggregate_stats()


@router.post("/batch")
async def batch_tasks(body: Dict[str, Any]):
    """批量导出(zip)/ 批量重跑(契约 §4.1 ``POST /tasks/batch``)。"""
    action = str(body.get("action") or "").strip().lower()
    task_ids = body.get("task_ids") or []
    if not isinstance(task_ids, list):
        raise HTTPException(status_code=400, detail="task_ids 必须是数组")

    svc = get_task_service()
    try:
        result = svc.batch(task_ids, action)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if result["action"] == "export":
        from fastapi.responses import Response

        return Response(
            content=result["zip_bytes"],
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=vid2note-export.zip"},
        )
    # rerun
    return {
        "action": "rerun",
        "new_task_ids": result["new_task_ids"],
        "count": result["count"],
    }


# --------------------------------------------------------------------------- #
# 详情 / 流 / 重跑 / 取消 / 下载
# --------------------------------------------------------------------------- #
def _get_task_or_404(task_id: str):
    task = get_task_service().get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在:{task_id}")
    return task


@router.get("/{task_id}")
async def get_task(task_id: str):
    """任务详情(契约 §4.1 ``GET /tasks/{id}``)。"""
    return _get_task_or_404(task_id).to_dict()


@router.get("/{task_id}/stream")
async def stream_task(task_id: str):
    """SSE 实时进度 / 日志(契约 §4.1 / §6.8)。"""
    # 任务不存在也允许连入(流内推 task-missing 后正常关闭)
    return StreamingResponse(
        _stream_events(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 关闭 nginx 缓冲,SSE 立即下发
        },
    )


@router.post("/{task_id}/rerun")
async def rerun_task(
    task_id: str,
    from_node: Optional[str] = Query(None, alias="from", description="起始节点(六节点之一)"),
):
    """节点级重跑(契约 §4.1 / §5.3)。``from`` 为 Python 关键字,用 alias 映射。"""
    svc = get_task_service()
    try:
        task = svc.rerun(task_id, from_node)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"任务不存在:{task_id}")
    except ValueError as exc:
        # 状态不允许重跑(pending/running)或 from_node 非法 → 409
        raise HTTPException(status_code=409, detail=str(exc))
    return {"task_id": task.id, "status": task.status.value if hasattr(task.status, "value") else str(task.status),
            "from_node": from_node}


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    """取消任务(契约 §0.6 / §4.1)。"""
    svc = get_task_service()
    try:
        ok = svc.cancel(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"任务不存在:{task_id}")
    if not ok:
        # 终态任务无法取消 → 409
        raise HTTPException(status_code=409, detail="任务已结束,无法取消")
    return {"task_id": task_id, "cancelled": True}


@router.get("/{task_id}/products/{kind}")
async def download_product(
    task_id: str,
    kind: str,
    index: int = Query(0, ge=0, description="列表类产物(mindmap/screenshot)的序号"),
):
    """下载产物(契约 §4.1;is_safe_path 防越界)。"""
    if kind not in {"note", "srt", "video", "audio", "mindmap", "screenshot", "pdf"}:
        raise HTTPException(status_code=400, detail=f"不支持的产物类型:{kind}")

    task = _get_task_or_404(task_id)
    rel = _resolve_product_rel(task, kind, index)
    if not rel:
        raise HTTPException(status_code=404, detail=f"该任务没有可下载的 {kind} 产物")

    svc = get_task_service()
    data_root = Path(svc.data_root).resolve()
    abs_path = (data_root / rel).resolve()
    # 防路径遍历(契约 §4.1):产物必须在 DATA_ROOT 内
    if not is_safe_path(data_root, abs_path) or not abs_path.exists() or not abs_path.is_file():
        raise HTTPException(status_code=404, detail="产物文件不存在或路径非法")

    media_type, _ = mimetypes.guess_type(abs_path.name)
    # PDF 讲义用于笔记页 iframe 内联预览,不带 attachment 头(否则浏览器下载而非显示);
    # 其余产物带文件名供 <a download> 下载。
    if kind == "pdf":
        return FileResponse(str(abs_path), media_type=media_type or "application/pdf")
    return FileResponse(
        str(abs_path),
        media_type=media_type or "application/octet-stream",
        filename=abs_path.name,
    )
