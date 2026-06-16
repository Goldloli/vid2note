"""SQLite 数据库管理"""

import atexit
import contextlib
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional


class Database:
    _instance: Optional["Database"] = None
    _lock = threading.Lock()
    _initialized: bool = False

    def __new__(cls, db_path: str | None = None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: str | None = None):
        if self._initialized:
            return
        if db_path is None:
            db_dir = Path("data")
            db_dir.mkdir(exist_ok=True, parents=True)
            db_path = str(db_dir / "tasks.db")
        self.db_path = db_path
        self._local = threading.local()
        self._initialized = True
        self._connections: set = set()
        self._connections_lock = threading.Lock()
        self._init_db()
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
                    audio_file TEXT
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
        if cls._instance:
            cls._instance.close_all_connections()
            with contextlib.suppress(Exception):
                Path(cls._instance.db_path).unlink(missing_ok=True)
        cls._instance = None
