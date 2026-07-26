"""存储用量统计(vid2note v1 · design D9 / spec storage-retention / CONTRACT §6.7)。

供 ``GET /api/v1/storage/stats`` 使用,统计 Docker volume 内五类产物目录的占用:
- 总量(字节数 + 人类可读单位);
- 按五类产物(video/audio/srt/note/screenshot)分别占用;
- 占用最高的若干任务(Top N)。

说明:``total_bytes`` 仅统计五类**产物**目录(与 spec「产物目录总占用」一致),
``temp/`` 临时目录单独统计为 ``temp_bytes``,不计入产物总量。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .cleaner import KIND_DIR, PRODUCT_KINDS, _dir_size

#: 人类可读单位(1024 进制)。
_UNITS = ["B", "KB", "MB", "GB", "TB", "PB"]


def format_bytes(num: Any) -> str:
    """字节数 → 人类可读字符串(1024 进制,如 ``1.5 GB`` / ``320 MB`` / ``512 B``)。"""
    try:
        n = int(num)
    except (TypeError, ValueError):
        n = 0
    if n < 0:
        n = 0

    size = float(n)
    unit_idx = 0
    while size >= 1024 and unit_idx < len(_UNITS) - 1:
        size /= 1024.0
        unit_idx += 1

    if unit_idx == 0:
        return f"{n} B"
    return f"{size:.1f} {_UNITS[unit_idx]}"


def _task_id_of(path: Path, kind_dir: Path) -> str | None:
    """文件归属的 task_id(kind_dir 下第一段路径分量)。"""
    try:
        rel = path.relative_to(kind_dir)
    except ValueError:
        return None
    parts = rel.parts
    if not parts:
        return None
    return parts[0]


def storage_stats(data_root: Any, top_n: int = 10) -> dict[str, Any]:
    """统计产物目录占用。

    Args:
        data_root: 产物根目录(DATA_ROOT)。
        top_n: 返回占用最高的前 N 个任务(默认 10)。

    Returns:
        ````python
        {
            "total_bytes": int,            # 五类产物总字节
            "total_human": str,            # 人类可读
            "by_kind": {kind: int, ...},   # 五类各自字节
            "by_kind_human": {kind: str},  # 五类各自人类可读
            "top_tasks": [                 # 占用最高任务(降序)
                {"task_id": str, "bytes": int, "bytes_human": str}, ...
            ],
            "temp_bytes": int,             # temp 目录字节(不计入产物总量)
            "temp_human": str,
        }
        ````
    """
    root = Path(data_root)
    by_kind: dict[str, int] = {kind: 0 for kind in PRODUCT_KINDS}
    per_task: dict[str, int] = {}

    for kind in PRODUCT_KINDS:
        kind_dir = root / KIND_DIR[kind]
        if not kind_dir.exists():
            continue
        for f in kind_dir.rglob("*"):
            if not f.is_file():
                continue
            try:
                size = f.stat().st_size
            except OSError:
                continue
            by_kind[kind] += size
            task_id = _task_id_of(f, kind_dir)
            if task_id:
                per_task[task_id] = per_task.get(task_id, 0) + size

    total_bytes = sum(by_kind.values())

    ranked = sorted(per_task.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    top_tasks = [
        {"task_id": tid, "bytes": b, "bytes_human": format_bytes(b)}
        for tid, b in ranked
    ]

    temp_bytes = _dir_size(root / "temp")

    return {
        "total_bytes": total_bytes,
        "total_human": format_bytes(total_bytes),
        "by_kind": {kind: by_kind[kind] for kind in PRODUCT_KINDS},
        "by_kind_human": {
            kind: format_bytes(by_kind[kind]) for kind in PRODUCT_KINDS
        },
        "top_tasks": top_tasks,
        "temp_bytes": temp_bytes,
        "temp_human": format_bytes(temp_bytes),
    }


__all__ = ["format_bytes", "storage_stats"]
