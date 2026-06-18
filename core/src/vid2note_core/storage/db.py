"""SQLite 数据库管理"""

import atexit
import contextlib
import sqlite3
import threading
import weakref
from contextlib import contextmanager
from pathlib import Path


class Database:
    _instances: weakref.WeakSet["Database"] = weakref.WeakSet()

    def __init__(self, db_path: str | Path):
        path = Path(db_path)
        if path != Path(":memory:"):
            path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(path)
        self._local = threading.local()
        self._connections: set = set()
        self._connections_lock = threading.Lock()
        self._init_db()
        self._instances.add(self)
        atexit.register(self.close_all_connections)

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "connection") or self._local.connection is None:
            self._local.connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.connection.row_factory = sqlite3.Row
            with self._connections_lock:
                self._connections.add(self._local.connection)
        return self._local.connection

    @contextmanager
    def get_connection(self):
        conn = self._get_connection()
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.commit()

    def _init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'pending',
                    progress INTEGER DEFAULT 0,
                    current_step TEXT DEFAULT '',
                    message TEXT,
                    download_url TEXT,
                    mindmap_url TEXT,
                    srt_file TEXT,
                    txt_file TEXT,
                    pdf_file TEXT,
                    output_file TEXT,
                    mindmap_file TEXT,
                    srt_original_name TEXT,
                    txt_original_name TEXT,
                    pdf_original_name TEXT,
                    title TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    extract_images BOOLEAN DEFAULT 0,
                    export_mindmap BOOLEAN DEFAULT 0,
                    mindmap_format TEXT DEFAULT 'xmind',
                    llm_provider TEXT,
                    llm_model TEXT,
                    error_message TEXT,
                    asr_provider TEXT,
                    video_url TEXT,
                    video_file TEXT,
                    audio_file TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    error_code TEXT,
                    error_retryable INTEGER NOT NULL DEFAULT 0,
                    rerun_from_node TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_nodes (
                    task_id TEXT NOT NULL,
                    node_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    artifacts TEXT,
                    metadata TEXT,
                    error TEXT,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    PRIMARY KEY (task_id, node_name)
                )
            """)
            conn.commit()
        self._migrate_db()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_status ON tasks(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_created ON tasks(created_at)")
            conn.commit()

    def _migrate_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(tasks)")
            columns = {r[1] for r in cursor.fetchall()}
            new_cols = {
                "progress": "INTEGER DEFAULT 0",
                "current_step": "TEXT DEFAULT ''",
                "message": "TEXT",
                "download_url": "TEXT",
                "mindmap_url": "TEXT",
                "srt_file": "TEXT",
                "txt_file": "TEXT",
                "pdf_file": "TEXT",
                "output_file": "TEXT",
                "mindmap_file": "TEXT",
                "srt_original_name": "TEXT",
                "txt_original_name": "TEXT",
                "pdf_original_name": "TEXT",
                "title": "TEXT",
                "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                "completed_at": "TIMESTAMP",
                "extract_images": "BOOLEAN DEFAULT 0",
                "export_mindmap": "BOOLEAN DEFAULT 0",
                "mindmap_format": "TEXT DEFAULT 'xmind'",
                "llm_provider": "TEXT",
                "llm_model": "TEXT",
                "error_message": "TEXT",
                "asr_provider": "TEXT",
                "video_url": "TEXT",
                "video_file": "TEXT",
                "audio_file": "TEXT",
                "retry_count": "INTEGER NOT NULL DEFAULT 0",
                "error_code": "TEXT",
                "error_retryable": "INTEGER NOT NULL DEFAULT 0",
                "rerun_from_node": "TEXT",
            }
            for col, dtype in new_cols.items():
                if col not in columns:
                    cursor.execute(f"ALTER TABLE tasks ADD COLUMN {col} {dtype}")
            conn.commit()

    def close(self):
        if hasattr(self._local, "connection") and self._local.connection:
            with self._connections_lock:
                self._connections.discard(self._local.connection)
            self._local.connection.close()
            self._local.connection = None

    def close_all_connections(self):
        with self._connections_lock:
            for conn in list(self._connections):
                with contextlib.suppress(Exception):
                    conn.close()
            self._connections.clear()

    def execute(self, sql: str, parameters: tuple = ()):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, parameters)
            return cursor

    def fetchone(self, sql: str, parameters: tuple = ()):
        return self.execute(sql, parameters).fetchone()

    def fetchall(self, sql: str, parameters: tuple = ()):
        return self.execute(sql, parameters).fetchall()

    @classmethod
    def reset_instance(cls):
        for instance in list(cls._instances):
            instance.close_all_connections()
        cls._instances.clear()
