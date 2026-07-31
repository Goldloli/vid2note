"""
数据库连接管理(v1 重写)

使用 SQLite 持久化任务与设置。严格依据 CONTRACT §3:
- 新 ``tasks`` 表 schema(契约 §3.1,六步 DAG + 视频/音频/链接来源)。
- 新增 ``settings`` 表(key/value,契约 §3.2)。
- 启用 WAL / synchronous=NORMAL / foreign_keys=ON(契约 §3.3)。
- 迁移:开发期直接 DROP 旧 ``tasks`` 重建(无生产数据),并确保 ``settings`` 表存在(契约 §3.4)。
"""
import sqlite3
import threading
import atexit
from pathlib import Path
from typing import Optional
from contextlib import contextmanager


# ---------------------------------------------------------------------------
# DDL 常量(契约 §3.1 / §3.2)
# ---------------------------------------------------------------------------
_TASKS_DDL = """
CREATE TABLE IF NOT EXISTS tasks (
    id               TEXT PRIMARY KEY,
    source_type      TEXT NOT NULL,
    source_url       TEXT,
    title            TEXT,
    status           TEXT NOT NULL DEFAULT 'pending',
    progress         INTEGER DEFAULT 0,
    video_path       TEXT,
    audio_path       TEXT,
    srt_path         TEXT,
    note_path        TEXT,
    pdf_path         TEXT,
    mindmap_paths    TEXT DEFAULT '[]',      -- JSON 数组
    screenshot_paths TEXT DEFAULT '[]',      -- JSON 数组
    node_statuses    TEXT DEFAULT '{}',      -- JSON 对象(六节点)
    llm_usage        TEXT NOT NULL DEFAULT '{}', -- JSON 对象(LLM 用量聚合)
    llm_provider     TEXT,
    llm_model        TEXT,
    asr_engine       TEXT,
    pdf_mode         TEXT DEFAULT 'pypdf',
    extract_images   BOOLEAN DEFAULT 0,
    output_language  TEXT DEFAULT 'zh',
    note_detail_level TEXT NOT NULL DEFAULT 'balanced',
    mindmap_formats  TEXT DEFAULT '["xmind"]', -- JSON 数组
    queue_position   INTEGER,
    error            TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at      TIMESTAMP
);
"""

_SETTINGS_DDL = """
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,                -- 标量存字面量;复杂值存 JSON
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# 索引:沿用基底(idx_status / idx_created_at)+ 新增 idx_source_type(便于历史筛选)
_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_status      ON tasks(status);",
    "CREATE INDEX IF NOT EXISTS idx_created_at  ON tasks(created_at);",
    "CREATE INDEX IF NOT EXISTS idx_source_type ON tasks(source_type);",
)

# 新 schema 关键判别列:旧表必然缺失这些列
_NEW_SCHEMA_DISCRIMINATOR = frozenset(
    {"source_type", "node_statuses", "mindmap_paths", "queue_position"}
)


class Database:
    """SQLite 数据库管理器(单例)"""

    _instance: Optional['Database'] = None
    _lock = threading.Lock()

    def __new__(cls, db_path: Optional[str] = None):
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: Optional[str] = None):
        if self._initialized:
            return

        # 默认数据库路径(支持环境变量覆盖,方便容器化部署)
        if db_path is None:
            import os
            env_db_path = os.environ.get("DB_PATH")
            if env_db_path:
                db_path = env_db_path
            else:
                project_root = Path(__file__).parent.parent.parent.parent
                db_dir = project_root / "data"
                db_dir.mkdir(exist_ok=True, parents=True)
                db_path = db_dir / "tasks.db"

        self.db_path = str(db_path)
        self._local = threading.local()
        self._initialized = True
        # 跟踪所有创建的连接,用于关闭时清理
        self._connections: set = set()
        self._connections_lock = threading.Lock()

        # 初始化数据库
        self._init_db()

        # 注册程序退出时的清理函数
        atexit.register(self.close_all_connections)

    def _get_connection(self) -> sqlite3.Connection:
        """获取线程本地连接(契约 §3.3:建连后设置 PRAGMA)"""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            # journal_mode=DELETE:不用 WAL。Docker Desktop bind mount(osxfs/virtiofs)对
            # WAL 的 -shm/-wal(mmap+文件锁)支持不可靠,会触发 "disk I/O error" 使任务读写
            # 失败;DELETE 用 rollback journal,兼容 bind mount。synchronous=NORMAL 安全且快。
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.row_factory = sqlite3.Row
            self._local.connection = conn
            # 跟踪此连接
            with self._connections_lock:
                self._connections.add(self._local.connection)
        return self._local.connection

    @contextmanager
    def get_connection(self):
        """上下文管理器获取连接"""
        conn = self._get_connection()
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.commit()

    def _init_db(self):
        """初始化数据库表结构(契约 §3.1 / §3.2 新 schema)。

        关键顺序:先迁移(旧库 DROP 旧 tasks),再建新表与索引——
        否则在旧表上创建 ``idx_source_type`` 会因列缺失而失败。
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. 迁移:旧 schema 先 DROP(幂等;新库/新表为 no-op)
            self._migrate_db(cursor)

            # 2. 创建任务表(v1 新 schema;IF NOT EXISTS 对新库/已迁移库均安全)
            cursor.execute(_TASKS_DDL)

            # 3. 创建索引(此时 tasks 必为新 schema)
            for index_sql in _INDEXES:
                cursor.execute(index_sql)

            # 4. 创建设置表(_migrate_db 已确保,此处幂等再保险)
            cursor.execute(_SETTINGS_DDL)

            conn.commit()
            print(f"[Database] Initialized at {self.db_path}")

    def _migrate_db(self, cursor=None):
        """数据库迁移(契约 §3.4)。

        - 旧 ``tasks`` schema(缺失新判别列):开发期直接 DROP,由调用方
          随后的 ``CREATE TABLE`` 重建为 v1 新 schema。工作区已清空、无生产数据,
          故不做逐列 ALTER 与数据搬运。
        - 确保 ``settings`` 表存在(幂等)。

        可独立调用(自取连接),也可由 :meth:`_init_db` 传入 cursor 复用同一事务。
        """
        owns_conn = cursor is None
        if owns_conn:
            conn = self._get_connection()
            cursor = conn.cursor()
        try:
            # 读取现有 tasks 列,判断是否为旧 schema
            cursor.execute("PRAGMA table_info(tasks)")
            existing_cols = {row[1] for row in cursor.fetchall()}

            if existing_cols and not _NEW_SCHEMA_DISCRIMINATOR.issubset(existing_cols):
                # 旧 schema → DROP(连同其索引一并丢弃),由后续 CREATE 重建为新 schema
                cursor.execute("DROP TABLE IF EXISTS tasks")
                print("[Database] 检测到旧 tasks schema,已 DROP,将以 v1 新 schema 重建")
            elif existing_cols and "note_detail_level" not in existing_cols:
                cursor.execute(
                    "ALTER TABLE tasks ADD COLUMN note_detail_level "
                    "TEXT NOT NULL DEFAULT 'balanced'"
                )
            elif existing_cols and "llm_usage" not in existing_cols:
                cursor.execute(
                    "ALTER TABLE tasks ADD COLUMN llm_usage "
                    "TEXT NOT NULL DEFAULT '{}'"
                )

            # 确保 settings 表存在(幂等)
            cursor.execute(_SETTINGS_DDL)

            if owns_conn:
                conn.commit()
        except Exception:
            if owns_conn:
                conn.rollback()
            raise

    def close(self):
        """关闭当前线程的数据库连接"""
        if hasattr(self._local, 'connection') and self._local.connection:
            with self._connections_lock:
                self._connections.discard(self._local.connection)
            self._local.connection.close()
            self._local.connection = None

    def close_all_connections(self):
        """关闭所有跟踪的数据库连接（用于程序退出时清理）"""
        with self._connections_lock:
            for conn in list(self._connections):
                try:
                    conn.close()
                except Exception:
                    pass  # 忽略关闭时的错误
            self._connections.clear()
        print("[Database] All connections closed")

    def execute(self, sql: str, parameters: tuple = ()):
        """执行 SQL 语句"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, parameters)
            return cursor

    def fetchone(self, sql: str, parameters: tuple = ()):
        """查询单条记录"""
        cursor = self.execute(sql, parameters)
        return cursor.fetchone()

    def fetchall(self, sql: str, parameters: tuple = ()):
        """查询多条记录"""
        cursor = self.execute(sql, parameters)
        return cursor.fetchall()

    @classmethod
    def reset_instance(cls):
        """重置单例（用于测试）"""
        if cls._instance:
            cls._instance.close_all_connections()
        cls._instance = None
