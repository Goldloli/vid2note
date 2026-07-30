"""
任务数据访问层(v1 重写)

提供 ``tasks`` 与 ``settings`` 两表的读写,严格依据 CONTRACT §1 / §3。
所有写路径集中于此(契约 §3.3):不得散落到其它模块。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from .database import Database
except ImportError:  # 兼容内核单测的裸 import
    from db.database import Database
try:
    from ..models.task import Task, TaskStatus, default_node_statuses
except ImportError:  # 兼容内核单测的裸 import
    from models.task import Task, TaskStatus, default_node_statuses


# JSON 列:落库前需 json.dumps
_JSON_COLUMNS: frozenset[str] = frozenset(
    {"mindmap_paths", "screenshot_paths", "node_statuses", "mindmap_formats"}
)

# 状态字面量(避免频繁枚举转换)
_PENDING = TaskStatus.PENDING.value
_RUNNING = TaskStatus.RUNNING.value
_COMPLETED = TaskStatus.COMPLETED.value
_FAILED = TaskStatus.FAILED.value
_CANCELLED = TaskStatus.CANCELLED.value


def _status_value(value: Any) -> str:
    """把 TaskStatus / 字符串归一为状态字面量。"""
    if isinstance(value, TaskStatus):
        return value.value
    return str(value)


def _encode_field(key: str, value: Any) -> Any:
    """编码单个字段为可入库的标量(JSON 列 dumps / 枚举取值 / datetime 取 ISO)。"""
    if key in _JSON_COLUMNS:
        if value is None:
            return "[]" if key != "node_statuses" else "{}"
        if isinstance(value, str):
            return value  # 已是 JSON 字符串,原样落库
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, TaskStatus):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bool):
        # BOOLEAN 列:显式落 0/1,避免不同 sqlite 版本差异
        return 1 if value else 0
    return value


class TaskRepository:
    """任务数据仓库(契约 §3 / §1)"""

    def __init__(self, db: Optional[Database] = None):
        """初始化仓库"""
        self.db = db or Database()

    # ------------------------------------------------------------------
    # 基础 CRUD
    # ------------------------------------------------------------------
    def create(self, task: Task) -> str:
        """创建任务(契约 §1.1 全部新字段;JSON 列 dumps;返回任务 ID)。

        pending 任务初始 queue_position 取当前排队位次(FIFO 缓存,
        权威位次以 :meth:`queue_position_of` 实时计算为准)。
        """
        # 入队时计算初始排队位次(仅 pending 任务有意义)
        queue_position = task.queue_position
        if queue_position is None and task.status == TaskStatus.PENDING:
            row = self.db.fetchone(
                "SELECT COUNT(*) AS c FROM tasks WHERE status = ?",
                (_PENDING,),
            )
            ahead = row["c"] if row and row["c"] else 0
            queue_position = int(ahead) + 1

        sql = """
            INSERT INTO tasks (
                id, source_type, source_url, title, status, progress,
                video_path, audio_path, srt_path, note_path, pdf_path,
                mindmap_paths, screenshot_paths, node_statuses,
                llm_provider, llm_model, asr_engine,
                pdf_mode, extract_images, output_language, note_detail_level,
                mindmap_formats,
                queue_position, error, created_at, updated_at, finished_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?
            )
        """

        params = (
            task.id,
            task.source_type,
            task.source_url,
            task.title,
            task.status.value,
            task.progress,
            task.video_path,
            task.audio_path,
            task.srt_path,
            task.note_path,
            task.pdf_path,
            json.dumps(list(task.mindmap_paths), ensure_ascii=False),
            json.dumps(list(task.screenshot_paths), ensure_ascii=False),
            json.dumps(task.node_statuses, ensure_ascii=False),
            task.llm_provider,
            task.llm_model,
            task.asr_engine,
            task.pdf_mode,
            1 if task.extract_images else 0,
            task.output_language,
            task.note_detail_level,
            json.dumps(list(task.mindmap_formats), ensure_ascii=False),
            queue_position,
            task.error,
            task.created_at.isoformat() if task.created_at else datetime.now().isoformat(),
            task.updated_at.isoformat() if task.updated_at else datetime.now().isoformat(),
            task.finished_at.isoformat() if task.finished_at else None,
        )

        self.db.execute(sql, params)
        return task.id

    def get_by_id(self, task_id: str) -> Optional[Task]:
        """根据 ID 获取任务,不存在返回 None。"""
        row = self.db.fetchone(
            "SELECT * FROM tasks WHERE id = ?",
            (task_id,),
        )
        if row:
            return Task.from_db_row(row)
        return None

    def update(self, task_id: str, **kwargs) -> bool:
        """更新任务字段(自动刷新 updated_at)。

        JSON 列(mindmap_paths / screenshot_paths / node_statuses / mindmap_formats)
        传 list/dict 时自动 dumps;枚举/datetime 自动取值;返回是否命中。
        """
        if not kwargs:
            # 无字段也要刷一次 updated_at
            kwargs = {}

        # 自动更新 updated_at(调用方显式传入则尊重)
        kwargs.setdefault("updated_at", datetime.now())

        # 维护 queue_position 不变量(契约 §1.1):running / 终态任务的位次恒为 None。
        # 仅当调用方未显式指定 queue_position 时介入,避免覆盖显式赋值。
        new_status = kwargs.get("status")
        if new_status is not None and _status_value(new_status) != _PENDING:
            kwargs.setdefault("queue_position", None)

        fields: List[str] = []
        values: List[Any] = []
        for key, value in kwargs.items():
            fields.append(f"{key} = ?")
            values.append(_encode_field(key, value))

        values.append(task_id)
        sql = f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?"
        cursor = self.db.execute(sql, tuple(values))
        return cursor.rowcount > 0

    def delete(self, task_id: str) -> bool:
        """删除任务,返回是否命中。"""
        cursor = self.db.execute(
            "DELETE FROM tasks WHERE id = ?",
            (task_id,),
        )
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # 历史与统计
    # ------------------------------------------------------------------
    def list_history(
        self,
        status: Optional[Union[TaskStatus, str]] = None,
        source_type: Optional[str] = None,
        q: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """任务历史列表(契约 §3.4 / §4.1)。

        status / source_type / q(关键词,匹配 title / source_url / source_type,
        大小写不敏感)组合取**交集**;page 1-based。
        返回 ``{"items": [...], "total": int, "page": int, "page_size": int}``。
        """
        page = max(1, int(page))
        page_size = max(1, int(page_size))
        offset = (page - 1) * page_size

        where: List[str] = []
        params: List[Any] = []

        if status is not None and status != "":
            where.append("status = ?")
            params.append(_status_value(status))
        if source_type:
            where.append("source_type = ?")
            params.append(source_type)
        if q:
            like = f"%{q}%"
            where.append("(LOWER(title) LIKE LOWER(?) OR LOWER(source_url) LIKE LOWER(?) OR LOWER(source_type) LIKE LOWER(?))")
            params.extend([like, like, like])

        where_sql = f" WHERE {' AND '.join(where)}" if where else ""

        # 总数(同筛选条件)
        total_row = self.db.fetchone(
            f"SELECT COUNT(*) AS c FROM tasks{where_sql}",
            tuple(params),
        )
        total = int(total_row["c"]) if total_row and total_row["c"] else 0

        # 分页数据(按创建时间倒序)
        rows = self.db.fetchall(
            f"SELECT * FROM tasks{where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            tuple(params) + (page_size, offset),
        )
        items = [Task.from_db_row(row) for row in rows]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def aggregate_stats(self) -> Dict[str, int]:
        """运行态聚合统计(openspec change console-history-detail-nav ``GET /tasks/stats``)。

        返回 running(排队+运行中) / today_completed(今日完成) / total(累计) /
        completed(累计完成)。纯 SQL 聚合,无文件 IO。
        """
        def _count(sql: str, params: tuple = ()) -> int:
            row = self.db.fetchone(sql, params)
            return int(row["c"]) if row and row["c"] else 0

        today = datetime.now().date().isoformat()
        return {
            "running": _count("SELECT COUNT(*) AS c FROM tasks WHERE status IN ('pending','running')"),
            "today_completed": _count(
                "SELECT COUNT(*) AS c FROM tasks WHERE status='completed' AND finished_at LIKE ?",
                (f"{today}%",),
            ),
            "total": _count("SELECT COUNT(*) AS c FROM tasks"),
            "completed": _count("SELECT COUNT(*) AS c FROM tasks WHERE status='completed'"),
        }

    def list_all(
        self,
        status: Optional[Union[TaskStatus, str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Task]:
        """(向后兼容)任务列表,委托 :meth:`list_history`。"""
        result = self.list_history(status=status, page=1, page_size=limit)
        # list_history 用 OFFSET=(page-1)*page_size=0,这里手动截断以保留 offset 语义
        if offset:
            items = result["items"]
            return items[offset: offset + limit]
        return result["items"]

    def count_by_status(self, status: Union[TaskStatus, str]) -> int:
        """统计指定状态的任务数量。"""
        row = self.db.fetchone(
            "SELECT COUNT(*) AS c FROM tasks WHERE status = ?",
            (_status_value(status),),
        )
        return int(row["c"]) if row and row["c"] else 0

    def count_active(self) -> int:
        """统计活跃任务数量(pending + running)。"""
        row = self.db.fetchone(
            "SELECT COUNT(*) AS c FROM tasks WHERE status IN (?, ?)",
            (_PENDING, _RUNNING),
        )
        return int(row["c"]) if row and row["c"] else 0

    def get_pending_tasks(self, limit: int = 10) -> List[Task]:
        """获取待处理任务(FIFO,按 created_at 升序)。"""
        rows = self.db.fetchall(
            "SELECT * FROM tasks WHERE status = ? ORDER BY created_at ASC LIMIT ?",
            (_PENDING, limit),
        )
        return [Task.from_db_row(row) for row in rows]

    # ------------------------------------------------------------------
    # 队列
    # ------------------------------------------------------------------
    def queue_position_of(self, task_id: str) -> Optional[int]:
        """计算任务在 pending 队列中的 FIFO 位次(1 为队首)。

        权威计算:COUNT 排在前面的 pending 任务数 + 1;非 pending / 不存在返回 None。
        created_at 相同时以 id 作为稳定 tiebreaker。
        """
        row = self.db.fetchone(
            "SELECT created_at FROM tasks WHERE id = ? AND status = ?",
            (task_id, _PENDING),
        )
        if not row:
            return None
        target_created = row["created_at"]

        pos_row = self.db.fetchone(
            """
            SELECT COUNT(*) AS c FROM tasks
            WHERE status = ?
              AND (created_at < ? OR (created_at = ? AND id <= ?))
            """,
            (_PENDING, target_created, target_created, task_id),
        )
        return int(pos_row["c"]) if pos_row and pos_row["c"] else 1

    def reserve_pending_task(self, worker_id: Optional[str] = None) -> Optional[Task]:
        """原子性预留一个待处理任务(pending → running)。

        使用 SQLite 原子 ``UPDATE ... RETURNING``(契约 §3.4),保证并发下仅一个
        worker 取到同一任务。预留时清空 queue_position(运行态位次为 None)。
        无待处理任务返回 None。
        """
        now = datetime.now().isoformat()
        sql = """
            UPDATE tasks
            SET status = ?,
                queue_position = NULL,
                updated_at = ?
            WHERE id = (
                SELECT id FROM tasks
                WHERE status = ?
                ORDER BY created_at ASC
                LIMIT 1
            )
            RETURNING *
        """

        # RETURNING 需在同一连接内 fetch 后提交,不走 execute() 上下文
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(sql, (_RUNNING, now, _PENDING))
            row = cursor.fetchone()
            if row:
                conn.commit()
                return Task.from_db_row(row)
            conn.rollback()
            return None
        except Exception as e:
            # 不支持 RETURNING 时回退到事务方案
            print(f"[reserve_pending_task] RETURNING failed: {e}, using fallback")
            try:
                conn.rollback()
            except Exception:
                pass
            return self._reserve_pending_task_fallback(worker_id)

    def _reserve_pending_task_fallback(self, worker_id: Optional[str] = None) -> Optional[Task]:
        """预留任务的备选实现(用于不支持 RETURNING 的数据库,事务 + 行锁)。"""
        conn = self.db._get_connection()
        now = datetime.now().isoformat()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                """
                SELECT * FROM tasks
                WHERE status = ?
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (_PENDING,),
            )
            row = cursor.fetchone()
            if not row:
                conn.execute("COMMIT")
                return None

            task_id = row["id"]
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, queue_position = NULL, updated_at = ?
                WHERE id = ?
                """,
                (_RUNNING, now, task_id),
            )
            conn.execute("COMMIT")
            return self.get_by_id(task_id)
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            return None

    # ------------------------------------------------------------------
    # 启动恢复(契约 §0.9 / §3.4)
    # ------------------------------------------------------------------
    def reset_running_on_startup(self) -> int:
        """启动恢复:把残留 running 任务标 failed。

        error 注明「重启中断于 `<节点名>` 节点」(从 node_statuses 取当前 running 节点;
        无则注「重启中断,任务未正常结束」)。返回被重置的任务数。
        """
        rows = self.db.fetchall(
            "SELECT * FROM tasks WHERE status = ?",
            (_RUNNING,),
        )
        if not rows:
            return 0

        now = datetime.now().isoformat()
        count = 0
        for row in rows:
            task = Task.from_db_row(row)
            node_name = self._find_running_node(task)
            error = (
                f"重启中断于 {node_name} 节点"
                if node_name
                else "重启中断,任务未正常结束"
            )
            self.db.execute(
                """
                UPDATE tasks
                SET status = ?, error = ?, queue_position = NULL,
                    finished_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (_FAILED, error, now, now, task.id),
            )
            count += 1
        return count

    @staticmethod
    def _find_running_node(task: Task) -> Optional[str]:
        """从 node_statuses 中找出当前 running 的节点名(无则 None)。"""
        node_statuses = task.node_statuses or {}
        for name, info in node_statuses.items():
            if isinstance(info, dict) and info.get("status") == "running":
                return name
        return None

    # ------------------------------------------------------------------
    # 设置表(契约 §3.2)
    # ------------------------------------------------------------------
    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """读取单个设置项,不存在返回 default。"""
        row = self.db.fetchone(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        )
        if row is None:
            return default
        return row["value"]

    def set_setting(self, key: str, value: Any) -> None:
        """写入设置项(UPSERT)。复杂值由调用方自行 JSON 序列化为字符串。"""
        self.db.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, str(value), datetime.now().isoformat()),
        )

    def get_all_settings(self) -> Dict[str, str]:
        """读取全部设置项(key → value)。"""
        rows = self.db.fetchall("SELECT key, value FROM settings")
        return {row["key"]: row["value"] for row in rows}

    def delete_setting(self, key: str) -> None:
        """删除单个旧设置项（文件化设置迁移完成后清理敏感值）。"""
        self.db.execute("DELETE FROM settings WHERE key = ?", (key,))

    # ------------------------------------------------------------------
    # 便捷状态变更(新字段语义)
    # ------------------------------------------------------------------
    def fail_task(self, task_id: str, error: str) -> bool:
        """标记任务失败(记录中文错误,写 finished_at,清 queue_position)。"""
        now = datetime.now().isoformat()
        cursor = self.db.execute(
            """
            UPDATE tasks
            SET status = ?, error = ?, queue_position = NULL,
                finished_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (_FAILED, error, now, now, task_id),
        )
        return cursor.rowcount > 0

    def cancel_task(self, task_id: str) -> bool:
        """取消任务(写 finished_at,清 queue_position)。"""
        now = datetime.now().isoformat()
        cursor = self.db.execute(
            """
            UPDATE tasks
            SET status = ?, queue_position = NULL,
                finished_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (_CANCELLED, now, now, task_id),
        )
        return cursor.rowcount > 0
