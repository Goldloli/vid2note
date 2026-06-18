"""测试数据库管理"""

import sqlite3
import pytest
from vid2note_core.storage.db import Database


def test_database_instances_are_isolated():
    db1 = Database(":memory:")
    db2 = Database(":memory:")
    assert db1 is not db2


def test_init_creates_tables(tmp_path):
    db_path = tmp_path / "tasks.db"
    db = Database(str(db_path))
    with db.get_connection() as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cursor.fetchall()}
    assert "tasks" in tables
    assert "task_nodes" in tables


def test_migrations_add_mindmap_columns(tmp_path):
    db_path = tmp_path / "tasks.db"
    # 先创建旧版 schema（不含 mindmap_url）
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending'
        )
    """)
    conn.commit()
    conn.close()
    # 重新初始化应自动迁移
    Database.reset_instance()
    db = Database(str(db_path))
    with db.get_connection() as conn:
        cursor = conn.execute("PRAGMA table_info(tasks)")
        columns = {r[1] for r in cursor.fetchall()}
    assert "mindmap_url" in columns
