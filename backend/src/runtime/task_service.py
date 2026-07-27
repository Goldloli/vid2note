"""
runtime.task_service —— 任务编排服务(契约 §4 / §5.3 / 设计 D8)
==============================================================

对接 API 层,封装任务的创建 / 查询 / 重跑 / 取消 / 历史 / 批量,统一走
``TaskRepository`` 与运行队列,不直接碰 SQLite 细节。

公共方法:
- :meth:`create_task` —— ``identify_source`` + 写库 + 入队(本地文件搬到产物目录)。
- :meth:`get_task` —— 读单个任务。
- :meth:`rerun` —— 节点级重跑(复用上游产物,契约 §5.3);入队由 worker 执行。
- :meth:`cancel` —— pending→cancelled 移出队列;running→发取消信号;终态→拒绝。
- :meth:`list_history` —— 筛选 + 分页(委托 ``repo.list_history``)。
- :meth:`batch` —— 批量导出(zip)/ 批量重跑(为每项新建复用输入的任务)。
"""
from __future__ import annotations

import asyncio
import io
import json
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.kernel import TaskRepository, logger
from src.media_ingest import SourceType, UploadedFile, identify_source
from src.models.task import NODE_NAMES, TASK_STATUSES, TERMINAL_TASK_STATUSES, Task, TaskStatus
from src.utils.security import secure_filename

from .adapters import get_cancel_registry
from .runner import _default_data_root
from .settings import get_settings_snapshot
from .worker import enqueue, get_worker, mark_skip


_RUNNING = TaskStatus.RUNNING.value
_PENDING = TaskStatus.PENDING.value
_CANCELLED = TaskStatus.CANCELLED.value


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _new_task_id() -> str:
    """生成任务 ID:``task_<12hex>``(沿用基底 ``upload.generate_task_id`` 约定)。"""
    return f"task_{uuid.uuid4().hex[:12]}"


def _ext_from_mime(mime: str) -> str:
    """从 MIME 粗取扩展名(无则空串)。"""
    m = (mime or "").lower()
    mapping = {
        "video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov",
        "video/x-matroska": "mkv", "audio/mpeg": "mp3", "audio/wav": "wav",
        "audio/x-wav": "wav", "audio/mp4": "m4a", "audio/aac": "aac",
        "audio/ogg": "ogg", "audio/flac": "flac",
    }
    return mapping.get(m, "")


class TaskService:
    """任务编排服务(对 API 层的唯一入口)。"""

    def __init__(
        self,
        *,
        repo: Optional[TaskRepository] = None,
        data_root: Optional[Path] = None,
    ) -> None:
        self.repo = repo or TaskRepository()
        self.data_root = Path(data_root) if data_root else _default_data_root()
        self.data_root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # 创建任务
    # ------------------------------------------------------------------ #
    def create_task(
        self,
        source_url: Optional[str] = None,
        uploaded: Optional[UploadedFile] = None,
        *,
        title: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        asr_engine: Optional[str] = None,
        pdf_mode: Optional[str] = None,
        extract_images: Optional[bool] = None,
        output_language: Optional[str] = None,
        mindmap_formats: Optional[List[str]] = None,
        pdf_path: Optional[str] = None,
    ) -> Task:
        """创建任务(契约 §4.1 ``POST /api/v1/tasks``)。

        Args:
            source_url: 在线视频链接(``uploaded`` 为空时必须)。
            uploaded: 本地上传文件描述(``source_url`` 为空时必须)。
            title: 任务标题(默认取视频标题/上传文件名)。
            llm_provider / llm_model / asr_engine / pdf_mode / extract_images /
                output_language / mindmap_formats: 引擎选项;缺省从 settings 快照取合法默认。
            pdf_path: 用户附带的 PDF 讲义相对路径(输入,非产物)。

        Returns:
            已入库的 :class:`Task`(``status=pending``)。

        Raises:
            ValueError: 无法识别媒体来源(中文错误,API 回 400)。
        """
        source_type = identify_source(source_url, uploaded)  # 无法识别抛 ValueError
        snapshot = get_settings_snapshot(self.repo)
        task_id = _new_task_id()

        # 引擎选项缺省值(契约 §3.2 / §4.1)
        llm_provider = (llm_provider or snapshot.get("llm.provider") or "deepseek").strip().lower()
        llm_model = (llm_model or snapshot.get("llm.model") or "deepseek-v4-flash").strip()
        asr_engine = (asr_engine or snapshot.get("asr.engine") or "asrtools").strip().lower()
        pdf_mode = (pdf_mode or snapshot.get("pdf.mode") or "pypdf").strip().lower()
        if extract_images is None:
            extract_images = _as_bool(snapshot.get("note.extract_images"))
        output_language = (output_language or snapshot.get("note.output_language") or "zh").strip().lower()
        mindmap_formats = list(mindmap_formats) if mindmap_formats else ["xmind", "png", "md"]

        resolved_title = title
        if uploaded is not None and not resolved_title:
            resolved_title = uploaded.original_name

        task = Task(
            id=task_id,
            source_type=source_type.value,
            source_url=source_url if source_url else None,
            title=resolved_title,
            status=TaskStatus.PENDING,
            llm_provider=llm_provider,
            llm_model=llm_model,
            asr_engine=asr_engine,
            pdf_mode=pdf_mode,
            extract_images=bool(extract_images),
            output_language=output_language,
            mindmap_formats=mindmap_formats,
            pdf_path=str(pdf_path) if pdf_path else None,
        )

        # 本地来源:把上传文件搬到产物目录,登记顶层指针(skipped 节点的上游产物)
        if uploaded is not None:
            self._place_uploaded_file(task, uploaded, source_type)

        self.repo.create(task)
        enqueue(task_id)
        logger.info("任务已创建并入队 task=%s source_type=%s", task_id, source_type.value)
        return task

    def _place_uploaded_file(
        self, task: Task, uploaded: UploadedFile, source_type: SourceType
    ) -> None:
        """把本地上传文件复制到产物目录,登记 video_path / audio_path(契约 §5.5)。

        local_video → ``videos/<tid>/clip.<ext>``;local_audio → ``audio/<tid>/audio.<ext>``。
        用复制(非移动)保留原文件;产物目录按 task_id 二级隔离(契约 §2.2)。
        """
        src_path = Path(uploaded.abs_path)
        if not src_path.exists():
            logger.warning("上传文件不存在,跳过搬移:%s", uploaded.abs_path)
            return
        ext = Path(uploaded.original_name or uploaded.abs_path).suffix.lstrip(".").lower()
        if not ext:
            ext = _ext_from_mime(uploaded.mime)

        if source_type == SourceType.LOCAL_VIDEO:
            dst_dir = self.data_root / "videos" / task.id
            dst = dst_dir / f"clip.{ext or 'mp4'}"
        elif source_type == SourceType.LOCAL_AUDIO:
            dst_dir = self.data_root / "audio" / task.id
            dst = dst_dir / f"audio.{ext or 'wav'}"
        else:  # 理论不会进入(仅 local_* 上传)
            return

        dst_dir.mkdir(parents=True, exist_ok=True)
        try:
            if src_path.resolve() != dst.resolve():
                shutil.copy2(str(src_path), str(dst))
        except Exception:  # noqa: BLE001 - 复制失败不阻断创建,后续节点会因缺产物失败
            logger.error("复制上传文件失败 task=%s src=%s", task.id, uploaded.abs_path, exc_info=True)
            return

        rel = dst.relative_to(self.data_root).as_posix()
        if source_type == SourceType.LOCAL_VIDEO:
            task.video_path = rel
        else:
            task.audio_path = rel

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #
    def get_task(self, task_id: str) -> Optional[Task]:
        """读单个任务;不存在返回 None。"""
        return self.repo.get_by_id(task_id)

    def list_history(
        self,
        *,
        status: Optional[str] = None,
        source_type: Optional[str] = None,
        q: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """任务历史(委托 ``repo.list_history``,契约 §4.1 ``GET /api/v1/tasks``)。"""
        return self.repo.list_history(
            status=status, source_type=source_type, q=q, page=page, page_size=page_size
        )

    def aggregate_stats(self) -> Dict[str, int]:
        """运行态聚合统计(契约 §4.1 ``GET /api/v1/tasks/stats``)。"""
        return self.repo.aggregate_stats()

    # ------------------------------------------------------------------ #
    # 重跑
    # ------------------------------------------------------------------ #
    def rerun(self, task_id: str, from_node: Optional[str] = None) -> Task:
        """节点级重跑(契约 §5.3 / §4.1 ``POST /api/v1/tasks/{id}/rerun``)。

        Args:
            task_id: 任务 ID。
            from_node: 起始节点(六节点之一);``None`` 为完整重跑。

        Returns:
            原任务(状态未变,重跑由 worker 异步执行)。

        Raises:
            KeyError: 任务不存在。
            ValueError: 状态不允许重跑(pending/running)或 ``from_node`` 非法。
        """
        task = self.repo.get_by_id(task_id)
        if task is None:
            raise KeyError(f"任务不存在:{task_id}")
        status = task.status.value if hasattr(task.status, "value") else str(task.status)
        if status in (_PENDING, _RUNNING):
            raise ValueError("任务正在排队或运行,无法重跑")
        if from_node is not None and from_node not in NODE_NAMES:
            raise ValueError(f"from_node 必须是六节点之一:{list(NODE_NAMES)}")

        enqueue(task_id, from_node)
        logger.info("任务已入队重跑 task=%s from_node=%s", task_id, from_node)
        return task

    # ------------------------------------------------------------------ #
    # 取消
    # ------------------------------------------------------------------ #
    def cancel(self, task_id: str) -> bool:
        """取消任务(契约 §0.6 / §4.1 ``POST /api/v1/tasks/{id}/cancel``)。

        - pending → cancelled(移出队列 + 落库 + SSE)。
        - running → 发取消信号(DAG 在下个检查点转 cancelled)。
        - 终态(completed/failed/cancelled)→ 返回 ``False`` 表示无效。

        Returns:
            是否成功发起取消。

        Raises:
            KeyError: 任务不存在。
        """
        task = self.repo.get_by_id(task_id)
        if task is None:
            raise KeyError(f"任务不存在:{task_id}")
        status = task.status.value if hasattr(task.status, "value") else str(task.status)

        if status in TERMINAL_TASK_STATUSES:
            return False

        if status == _RUNNING:
            # 向运行中任务发取消信号(DAG 捕获后转 cancelled)
            signalled = get_cancel_registry().cancel(task_id)
            if not signalled:
                # 边界:运行态但未登记令牌,直接置 cancelled
                self.repo.cancel_task(task_id)
                self._publish_event(task_id, "task-cancelled", {"status": _CANCELLED})
            return True

        # pending:从队列移除 + 落库
        mark_skip(task_id)
        self.repo.cancel_task(task_id)
        self._publish_event(task_id, "task-cancelled", {"status": _CANCELLED})
        logger.info("任务已取消 task=%s (原状态 pending)", task_id)
        return True

    # ------------------------------------------------------------------ #
    # 批量
    # ------------------------------------------------------------------ #
    def batch(
        self,
        task_ids: List[str],
        action: str,
    ) -> Dict[str, Any]:
        """批量导出 / 重跑(契约 §4.1 ``POST /api/v1/tasks/batch``)。

        - ``action="export"``:把选中**已完成**任务的 note(+ 同任务 srt/mindmap)打包 zip,
          返回 ``{"action":"export","zip_bytes": bytes, "count": int}``。
        - ``action="rerun"``:为每个选中任务创建**复用其输入与配置**的新任务入队,
          原记录不变,返回 ``{"action":"rerun","new_task_ids": [...], "count": int}``。

        Raises:
            ValueError: ``action`` 非 export/rerun。
        """
        action = (action or "").strip().lower()
        task_ids = list(task_ids or [])
        if action == "export":
            zip_bytes, count = self._batch_export(task_ids)
            return {"action": "export", "zip_bytes": zip_bytes, "count": count}
        if action == "rerun":
            new_ids = self._batch_rerun(task_ids)
            return {"action": "rerun", "new_task_ids": new_ids, "count": len(new_ids)}
        raise ValueError("action 必须是 export 或 rerun")

    def _batch_export(self, task_ids: List[str]) -> tuple:
        """把选中 completed 任务的产物打包 zip(按 task_id 分目录)。"""
        buf = io.BytesIO()
        count = 0
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for tid in task_ids:
                task = self.repo.get_by_id(tid)
                if task is None:
                    continue
                for rel in self._collect_export_artifacts(task):
                    abs_path = self.data_root / rel
                    if not abs_path.exists():
                        continue
                    try:
                        data = abs_path.read_bytes()
                    except Exception:  # noqa: BLE001
                        logger.debug("导出读取失败 task=%s rel=%s", tid, rel, exc_info=True)
                        continue
                    safe_tid = secure_filename(tid) or tid
                    zf.writestr(f"{safe_tid}/{abs_path.name}", data)
                    count += 1
        if count == 0:
            return b"", 0
        return buf.getvalue(), count

    @staticmethod
    def _collect_export_artifacts(task: Task) -> List[str]:
        """收集可导出的产物相对路径(note 优先,其次 srt / mindmap)。"""
        rels: List[str] = []
        if task.note_path:
            rels.append(task.note_path)
        if task.srt_path:
            rels.append(task.srt_path)
        rels.extend(list(task.mindmap_paths or []))
        # 去重保序
        seen = set()
        out = []
        for r in rels:
            if r and r not in seen:
                seen.add(r)
                out.append(r)
        return out

    def _batch_rerun(self, task_ids: List[str]) -> List[str]:
        """为每个选中任务创建复用输入与配置的新任务入队(原记录不变)。"""
        new_ids: List[str] = []
        for tid in task_ids:
            src = self.repo.get_by_id(tid)
            if src is None:
                continue
            try:
                new_task = self._clone_task(src)
            except Exception:  # noqa: BLE001 - 单个克隆失败不阻断批量
                logger.error("批量重跑:克隆任务失败 src=%s", tid, exc_info=True)
                continue
            new_ids.append(new_task.id)
        return new_ids

    def _clone_task(self, src: Task) -> Task:
        """复用源任务的输入与配置创建新任务(批量重跑用)。"""
        snapshot = get_settings_snapshot(self.repo)
        new_id = _new_task_id()
        new_task = Task(
            id=new_id,
            source_type=src.source_type,
            source_url=src.source_url,
            title=src.title,
            status=TaskStatus.PENDING,
            llm_provider=src.llm_provider or snapshot.get("llm.provider") or "deepseek",
            llm_model=src.llm_model or snapshot.get("llm.model") or "deepseek-v4-flash",
            asr_engine=src.asr_engine or snapshot.get("asr.engine") or "asrtools",
            pdf_mode=src.pdf_mode or "pypdf",
            extract_images=bool(src.extract_images),
            output_language=src.output_language or "zh",
            mindmap_formats=list(src.mindmap_formats or ["xmind", "png", "md"]),
            pdf_path=src.pdf_path,
        )
        # 本地来源:复用源任务的音视频产物文件(复制到新任务产物目录)
        if src.source_type == SourceType.LOCAL_VIDEO.value and src.video_path:
            self._copy_artifact(src.video_path, new_id, "videos", "clip")
            new_task.video_path = self._rel_for_clone(new_id, "videos", "clip", src.video_path)
        elif src.source_type == SourceType.LOCAL_AUDIO.value and src.audio_path:
            self._copy_artifact(src.audio_path, new_id, "audio", "audio")
            new_task.audio_path = self._rel_for_clone(new_id, "audio", "audio", src.audio_path)

        self.repo.create(new_task)
        enqueue(new_id)
        return new_task

    def _copy_artifact(
        self, src_rel: str, new_id: str, kind_dir: str, base: str
    ) -> None:
        """把源产物文件复制到新任务的产物目录(批量重跑复用本地输入)。"""
        src_abs = self.data_root / src_rel
        if not src_abs.exists():
            return
        ext = src_abs.suffix.lstrip(".")
        dst_dir = self.data_root / kind_dir / new_id
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / f"{base}.{ext}"
        try:
            shutil.copy2(str(src_abs), str(dst))
        except Exception:  # noqa: BLE001
            logger.error("复制源产物失败 new_id=%s rel=%s", new_id, src_rel, exc_info=True)

    def _rel_for_clone(
        self, new_id: str, kind_dir: str, base: str, src_rel: str
    ) -> str:
        """构造克隆任务的产物相对路径(沿用源文件扩展名)。"""
        ext = Path(src_rel).suffix.lstrip(".")
        return f"{kind_dir}/{new_id}/{base}.{ext}"

    # ------------------------------------------------------------------ #
    # SSE 辅助(尽力而为;无可用事件循环时跳过,DB 已是权威态)
    # ------------------------------------------------------------------ #
    def _publish_event(self, task_id: str, event: str, payload: dict) -> None:
        """尽力推一个 SSE 事件。

        在事件循环线程内(如异步 API 处理器):``create_task`` 调度非阻塞任务;
        在线程外(如同步调用):跨线程投递到 worker 的事件循环。
        """
        try:
            from src.sse import get_bus

            bus = get_bus()
        except Exception:  # noqa: BLE001
            return
        try:
            loop = asyncio.get_running_loop()
            # 同线程:非阻塞调度
            loop.create_task(bus.publish(task_id, event, payload))
            return
        except RuntimeError:
            pass
        # 不在事件循环线程:借用 worker 的 loop
        try:
            worker = get_worker()
            loop = getattr(worker, "_loop", None)
        except Exception:  # noqa: BLE001
            loop = None
        if loop is not None and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(
                    bus.publish(task_id, event, payload), loop
                )
            except Exception:  # noqa: BLE001
                logger.debug("跨线程 SSE 推送失败 task=%s", task_id, exc_info=True)


# --------------------------------------------------------------------------- #
# 进程内单例
# --------------------------------------------------------------------------- #
_service: Optional[TaskService] = None


def get_task_service(*, repo: Optional[TaskRepository] = None) -> TaskService:
    """获取全局 TaskService 单例。"""
    global _service
    if _service is None or repo is not None:
        _service = TaskService(repo=repo)
    return _service


__all__ = ["TaskService", "get_task_service"]
