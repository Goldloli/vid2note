"""任务仓库"""

import json
from dataclasses import dataclass, field
from datetime import datetime

from vid2note_core.storage.db import Database
from vid2note_core.types import NodeStatus, TaskStatus


@dataclass
class TaskRecord:
    id: str
    status: TaskStatus
    progress: int = 0
    current_step: str = ""
    message: str | None = None
    video_url: str | None = None
    video_file: str | None = None
    audio_file: str | None = None
    srt_file: str | None = None
    srt_original_name: str | None = None
    txt_file: str | None = None
    pdf_file: str | None = None
    output_file: str | None = None
    mindmap_file: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    asr_provider: str | None = None
    export_mindmap: bool = False
    mindmap_format: str = "xmind"
    error_message: str | None = None
    retry_count: int = 0
    error_code: str | None = None
    error_retryable: bool = False
    rerun_from_node: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class TaskNodeRecord:
    task_id: str
    node_name: str
    status: NodeStatus
    artifacts: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    error: dict | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class TaskRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, task_id: str, **kwargs) -> TaskRecord | None:
        now = datetime.now().isoformat()
        fields = {
            "id": task_id,
            "status": kwargs.get("status", TaskStatus.PENDING.value),
            "video_url": kwargs.get("video_url"),
            "video_file": kwargs.get("video_file"),
            "audio_file": kwargs.get("audio_file"),
            "srt_file": kwargs.get("srt_file"),
            "srt_original_name": kwargs.get("srt_original_name"),
            "txt_file": kwargs.get("txt_file"),
            "pdf_file": kwargs.get("pdf_file"),
            "output_file": kwargs.get("output_file"),
            "mindmap_file": kwargs.get("mindmap_file"),
            "llm_provider": kwargs.get("llm_provider"),
            "llm_model": kwargs.get("llm_model"),
            "asr_provider": kwargs.get("asr_provider"),
            "export_mindmap": int(kwargs.get("export_mindmap", False)),
            "mindmap_format": kwargs.get("mindmap_format", "xmind"),
            "error_message": kwargs.get("error_message"),
            "created_at": now,
            "updated_at": now,
        }
        cols = ", ".join(fields.keys())
        placeholders = ", ".join(["?"] * len(fields))
        self.db.execute(
            f"INSERT INTO tasks ({cols}) VALUES ({placeholders})",
            tuple(fields.values()),
        )
        return self.get_by_id(task_id)

    def get_by_id(self, task_id: str) -> TaskRecord | None:
        row = self.db.fetchone("SELECT * FROM tasks WHERE id = ?", (task_id,))
        if not row:
            return None
        return self._row_to_task(row)

    def reserve_pending_task(self) -> TaskRecord | None:
        """原子预留一个 pending 任务，返回后状态变 running"""
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at LIMIT 1",
                (TaskStatus.PENDING.value,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            task_id = row["id"]
            conn.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ? AND status = ?",
                (
                    TaskStatus.RUNNING.value,
                    datetime.now().isoformat(),
                    task_id,
                    TaskStatus.PENDING.value,
                ),
            )
            if conn.total_changes == 0:
                return None  # 被别的线程抢走了
        return self.get_by_id(task_id)

    def update(self, task_id: str, **kwargs) -> bool:
        if not kwargs:
            return False
        fields = [f"{k} = ?" for k in kwargs]
        self.db.execute(
            f"UPDATE tasks SET {', '.join(fields)}, updated_at = ? WHERE id = ?",
            (*list(kwargs.values()), datetime.now().isoformat(), task_id),
        )
        return True

    def update_node(
        self,
        task_id: str,
        node_name: str,
        status: NodeStatus,
        artifacts: list | None = None,
        metadata: dict | None = None,
        error: dict | None = None,
    ) -> None:
        now = datetime.now().isoformat()
        self.db.execute(
            """INSERT OR REPLACE INTO task_nodes
               (task_id, node_name, status, artifacts, metadata, error, started_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task_id,
                node_name,
                status.value,
                json.dumps(artifacts or []),
                json.dumps(metadata or {}),
                json.dumps(error) if error else None,
                now if status == NodeStatus.RUNNING else None,
                now if status in (NodeStatus.COMPLETED, NodeStatus.FAILED) else None,
            ),
        )

    def get_node(self, task_id: str, node_name: str) -> TaskNodeRecord | None:
        row = self.db.fetchone(
            "SELECT * FROM task_nodes WHERE task_id = ? AND node_name = ?",
            (task_id, node_name),
        )
        if not row:
            return None
        return TaskNodeRecord(
            task_id=row["task_id"],
            node_name=row["node_name"],
            status=NodeStatus(row["status"]),
            artifacts=json.loads(row["artifacts"] or "[]"),
            metadata=json.loads(row["metadata"] or "{}"),
            error=json.loads(row["error"]) if row["error"] else None,
        )

    def reset_task_for_rerun(self, task_id: str, from_node: str | None = None) -> None:
        """重置任务以重跑：清零进度、清错误、把状态改回 PENDING。

        from_node 为 None 时重跑整个 pipeline；否则只重置 from_node 及其下游节点状态
        （产物删除由 ArtifactStore.delete_downstream 负责，调用方处理）。
        """
        with self.db.get_connection() as conn:
            conn.execute(
                "UPDATE tasks SET status = ?, progress = 0, error_message = NULL, "
                "error_code = NULL, error_retryable = 0, current_step = NULL, "
                "rerun_from_node = ? WHERE id = ?",
                (TaskStatus.PENDING.value, from_node, task_id),
            )
            downstream = self._node_and_downstream(from_node) if from_node else None
            if downstream:
                placeholders = ",".join("?" * len(downstream))
                conn.execute(
                    f"UPDATE task_nodes SET status = 'pending', error = NULL, "
                    f"started_at = NULL, completed_at = NULL "
                    f"WHERE task_id = ? AND node_name IN ({placeholders})",
                    [task_id, *downstream],
                )
            else:
                conn.execute(
                    "UPDATE task_nodes SET status = 'pending', error = NULL, "
                    "started_at = NULL, completed_at = NULL WHERE task_id = ?",
                    (task_id,),
                )
            conn.commit()

    @staticmethod
    def _node_and_downstream(from_node: str) -> list[str]:
        """返回 from_node 及其拓扑下游的节点名列表。"""
        order = [
            "download",
            "extract_audio",
            "transcribe",
            "organize",
            "register_source",
            "propose_wiki_changes",
            "mindmap",
            "cleanup",
        ]
        try:
            idx = order.index(from_node)
        except ValueError:
            return []
        return order[idx:]

    def list_all(self, status: TaskStatus | None = None, limit: int = 100) -> list[TaskRecord]:
        if status:
            rows = self.db.fetchall(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status.value, limit),
            )
        else:
            rows = self.db.fetchall(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
            )
        return [self._row_to_task(r) for r in rows]

    def count_by_status(self, status: TaskStatus) -> int:
        row = self.db.fetchone("SELECT COUNT(*) FROM tasks WHERE status = ?", (status.value,))
        return row[0] if row else 0

    def count_active(self) -> int:
        row = self.db.fetchone(
            "SELECT COUNT(*) FROM tasks WHERE status IN (?, ?)",
            (TaskStatus.PENDING.value, TaskStatus.RUNNING.value),
        )
        return row[0] if row else 0

    def _row_to_task(self, row) -> TaskRecord:
        def _dt(val):
            return datetime.fromisoformat(val) if val else None

        return TaskRecord(
            id=row["id"],
            status=TaskStatus(row["status"]),
            progress=row["progress"] or 0,
            current_step=row["current_step"] or "",
            message=row["message"],
            video_url=row["video_url"],
            video_file=row["video_file"],
            audio_file=row["audio_file"],
            srt_file=row["srt_file"],
            srt_original_name=row["srt_original_name"],
            txt_file=row["txt_file"],
            pdf_file=row["pdf_file"],
            output_file=row["output_file"],
            mindmap_file=row["mindmap_file"],
            llm_provider=row["llm_provider"],
            llm_model=row["llm_model"],
            asr_provider=row["asr_provider"],
            export_mindmap=bool(row["export_mindmap"]),
            mindmap_format=row["mindmap_format"] or "xmind",
            error_message=row["error_message"],
            retry_count=row["retry_count"] or 0,
            error_code=row["error_code"],
            error_retryable=bool(row["error_retryable"]),
            rerun_from_node=row["rerun_from_node"],
            created_at=_dt(row["created_at"]),
            updated_at=_dt(row["updated_at"]),
            completed_at=_dt(row["completed_at"]),
        )
