"""产物保留策略 + 过期清理 + 存储统计(vid2note v1 · design D9 / spec storage-retention)。

对外公共 API:
- :func:`cleanup_expired` / :func:`run_cleanup_scan` / :func:`cleanup_task_temp`
- :func:`storage_stats` / :func:`format_bytes`
- :class:`RetentionPolicy` / :data:`PRODUCT_KINDS` / :class:`CleanupReport`

详见 ``cleaner.py`` 与 ``stats.py`` 模块文档。
"""
from .cleaner import (
    ACTIVE_STATUSES,
    DEFAULT_RETENTION_POLICIES,
    KIND_DIR,
    KIND_LIST_FIELDS,
    KIND_SCALAR_FIELD,
    PRODUCT_KINDS,
    TERMINAL_STATUSES,
    CleanupReport,
    RetentionPolicy,
    cleanup_expired,
    cleanup_task_temp,
    run_cleanup_scan,
)
from .stats import format_bytes, storage_stats

__all__ = [
    # 枚举 / 常量
    "RetentionPolicy",
    "PRODUCT_KINDS",
    "KIND_DIR",
    "KIND_SCALAR_FIELD",
    "KIND_LIST_FIELDS",
    "DEFAULT_RETENTION_POLICIES",
    "TERMINAL_STATUSES",
    "ACTIVE_STATUSES",
    # 清理
    "CleanupReport",
    "cleanup_expired",
    "run_cleanup_scan",
    "cleanup_task_temp",
    # 统计
    "storage_stats",
    "format_bytes",
]
