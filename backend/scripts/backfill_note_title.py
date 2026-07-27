"""一次性回填:把已完成任务的 task.title 更新为笔记 md 的首个 H1。

存量任务在「note 节点提取 H1 覆盖 title」特性上线前已生成笔记,title 未被覆盖。
本脚本读 data/notes 下每个笔记,提取 H1,回填 task.title。

用法:cd backend && .venv/bin/python scripts/backfill_note_title.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db.task_repository import TaskRepository  # noqa: E402

DATA_ROOT = Path(__file__).resolve().parents[2] / "data"


def main() -> int:
    repo = TaskRepository()
    res = repo.list_history(status="completed", page=1, page_size=1000)
    n = 0
    for t in res["items"]:
        if not t.note_path:
            continue
        p = DATA_ROOT / t.note_path
        if not p.exists():
            continue
        try:
            md = p.read_text(encoding="utf-8")
        except Exception:
            continue
        m = re.search(r"^#\s+(.+)$", md, re.MULTILINE)
        if not m:
            continue
        h1 = m.group(1).strip().strip("*`#_>").strip()
        if h1 and h1 != t.title:
            repo.update(t.id, title=h1)
            print(f"{t.id}: {t.title!r} -> {h1!r}")
            n += 1
    print(f"回填 {n} 个任务标题")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
