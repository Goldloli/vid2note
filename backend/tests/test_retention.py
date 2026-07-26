"""retention 模块单测(task 1.12 / 1.13 · design D9 / spec storage-retention)。

覆盖:
- 时钟快进 → 过期产物被删除;
- permanent 策略永不删;
- 未达终态(pending/running)任务的产物被跳过;
- 删除后同步置空 SQLite 产物引用(标量 + 列表字段);
- temp 目录:终态/孤儿任务被清,活跃任务保留;
- 五类策略互不影响;
- 存储统计字段齐全,且清理后用量下降幅度与删除文件大小一致。

说明:retention 对仓库采用依赖倒置(只依赖 get_by_id/update),本测试用 FakeRepo
模拟 v1 任务字段(video_path / … / mindmap_paths / screenshot_paths / status),
待 task 1.3/1.4 落地后真实 TaskRepository 无需改本模块即可对接。
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 让 `from src.xxx import ...` 可用(运行入口为 backend/)。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.retention import (
    DEFAULT_RETENTION_POLICIES,
    CleanupReport,
    RetentionPolicy,
    cleanup_expired,
    cleanup_task_temp,
    format_bytes,
    run_cleanup_scan,
    storage_stats,
)

# 固定「当前时间」,避免测试受宿主时钟影响。
NOW = datetime(2026, 7, 26, 12, 0, 0)

#: 测试用五类策略(显式覆盖默认,便于断言)。
POLICIES = {
    "retention.video": "7d",
    "retention.audio": "7d",
    "retention.srt": "30d",
    "retention.note": "permanent",
    "retention.screenshot": "30d",
}


# ---------------------------------------------------------------------------
# 测试替身:满足 retention 仓库协议(get_by_id / update)的 v1 任务记录。
# ---------------------------------------------------------------------------


class FakeTask:
    """v1 任务字段形态的测试替身(duck-typed)。"""

    def __init__(self, task_id: str, status: str = "completed", **product_fields):
        self.id = task_id
        self.status = status
        # v1 产物字段默认值
        self.video_path: str | None = None
        self.audio_path: str | None = None
        self.srt_path: str | None = None
        self.note_path: str | None = None
        self.pdf_path: str | None = None
        self.mindmap_paths: list[str] = []
        self.screenshot_paths: list[str] = []
        for key, val in product_fields.items():
            setattr(self, key, val)


class FakeRepo:
    def __init__(self):
        self.tasks: dict[str, FakeTask] = {}

    def add(self, task: FakeTask) -> FakeTask:
        self.tasks[task.id] = task
        return task

    def get_by_id(self, task_id: str):
        return self.tasks.get(task_id)

    def update(self, task_id: str, **kwargs) -> bool:
        t = self.tasks.get(task_id)
        if t is None:
            return False
        for k, v in kwargs.items():
            setattr(t, k, v)
        return True


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def write_file(path: Path, size: int = 10, age_days: float = 0.0) -> Path:
    """在 path 写入指定大小的文件,并把 mtime 设为 age_days 天前(相对 NOW)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    set_age(path, age_days)
    return path


def set_age(path: Path, age_days: float) -> None:
    ts = (NOW - timedelta(days=age_days)).timestamp()
    os.utime(path, (ts, ts))


def scan(repo, data_root, settings=POLICIES, now=NOW):
    """以注入时钟执行一次扫描。"""
    return run_cleanup_scan(repo, data_root, settings, clock=lambda: now)


# ---------------------------------------------------------------------------
# 清理:过期删除 / permanent 不删 / 未终态跳过
# ---------------------------------------------------------------------------


def test_clock_fast_forward_deletes_expired_and_nulls_reference(tmp_path):
    """7d 视频产物存在 8 天 → 删除,回收字节,SQLite video_path 置空。"""
    repo = FakeRepo()
    task = repo.add(
        FakeTask("task_a", status="completed", video_path="videos/task_a/clip.mp4")
    )
    clip = write_file(tmp_path / "videos" / "task_a" / "clip.mp4", size=1234, age_days=8)

    report = scan(repo, tmp_path)

    assert not clip.exists()
    assert "videos/task_a/clip.mp4" in report.deleted
    assert report.freed_bytes == 1234
    assert task.video_path is None  # SQLite 引用同步
    assert report.errors == []


def test_permanent_policy_never_deleted(tmp_path):
    """permanent 笔记即便超过 30 天也不删。"""
    repo = FakeRepo()
    repo.add(
        FakeTask("task_b", status="completed", note_path="notes/task_b/note.md")
    )
    note = write_file(tmp_path / "notes" / "task_b" / "note.md", size=200, age_days=40)
    # 思维导图与笔记同目录,同样 permanent 不删
    mindmap = write_file(
        tmp_path / "notes" / "task_b" / "note.xmind", size=80, age_days=40
    )
    repo.tasks["task_b"].mindmap_paths = ["notes/task_b/note.xmind"]

    report = scan(repo, tmp_path)

    assert note.exists()
    assert mindmap.exists()
    assert report.deleted == []
    assert report.freed_bytes == 0
    assert repo.tasks["task_b"].note_path == "notes/task_b/note.md"
    assert repo.tasks["task_b"].mindmap_paths == ["notes/task_b/note.xmind"]


def test_active_task_products_are_skipped(tmp_path):
    """running 任务的产物即便过期也被跳过,计入 skipped_active。"""
    repo = FakeRepo()
    repo.add(FakeTask("task_run", status="running", video_path="videos/task_run/v.mp4"))
    video = write_file(tmp_path / "videos" / "task_run" / "v.mp4", size=500, age_days=30)

    report = scan(repo, tmp_path)

    assert video.exists()
    assert report.deleted == []
    assert report.skipped_active >= 1
    # 引用保持不变
    assert repo.tasks["task_run"].video_path == "videos/task_run/v.mp4"


def test_pending_task_products_are_skipped(tmp_path):
    """pending 任务的产物同样跳过。"""
    repo = FakeRepo()
    repo.add(FakeTask("task_p", status="pending", video_path="videos/task_p/v.mp4"))
    video = write_file(tmp_path / "videos" / "task_p" / "v.mp4", size=10, age_days=30)

    report = scan(repo, tmp_path)

    assert video.exists()
    assert report.deleted == []
    assert report.skipped_active >= 1


def test_per_kind_policies_are_independent(tmp_path):
    """五类策略互不影响:video(7d) 删、srt(30d) 同龄(8 天)留。"""
    repo = FakeRepo()
    repo.add(
        FakeTask(
            "task_mix",
            status="completed",
            video_path="videos/task_mix/v.mp4",
            srt_path="srt/task_mix/a.srt",
        )
    )
    video = write_file(tmp_path / "videos" / "task_mix" / "v.mp4", size=100, age_days=8)
    srt = write_file(tmp_path / "srt" / "task_mix" / "a.srt", size=50, age_days=8)

    report = scan(repo, tmp_path)

    assert not video.exists()  # 7d 策略,8 天 → 删
    assert srt.exists()  # 30d 策略,8 天 → 留
    assert report.freed_bytes == 100
    assert repo.tasks["task_mix"].video_path is None
    assert repo.tasks["task_mix"].srt_path == "srt/task_mix/a.srt"


def test_screenshot_list_reference_partially_nulled(tmp_path):
    """截图列表字段:只删过期项,保留未过期项,引用按剩余文件过滤。"""
    repo = FakeRepo()
    repo.tasks["task_shot"] = FakeTask(
        "task_shot",
        status="completed",
        screenshot_paths=[
            "screenshots/task_shot/old.png",
            "screenshots/task_shot/new.png",
        ],
    )
    old = write_file(
        tmp_path / "screenshots" / "task_shot" / "old.png", size=300, age_days=40
    )
    new = write_file(
        tmp_path / "screenshots" / "task_shot" / "new.png", size=90, age_days=1
    )

    report = scan(repo, tmp_path)

    assert not old.exists()
    assert new.exists()
    assert report.freed_bytes == 300
    # 仅剩 new,引用被过滤
    assert repo.tasks["task_shot"].screenshot_paths == ["screenshots/task_shot/new.png"]


def test_note_kind_also_clears_mindmap_references(tmp_path):
    """note 类(notes/ 目录)过期清理后,note_path 与 mindmap_paths 同步置空。"""
    repo = FakeRepo()
    repo.tasks["task_n"] = FakeTask(
        "task_n",
        status="completed",
        note_path="notes/task_n/n.md",
        mindmap_paths=["notes/task_n/n.xmind", "notes/task_n/n.png"],
    )
    # 临时把 note 策略改成 7d,使笔记/导图过期
    policies = dict(POLICIES)
    policies["retention.note"] = "7d"
    md = write_file(tmp_path / "notes" / "task_n" / "n.md", size=100, age_days=10)
    xm = write_file(tmp_path / "notes" / "task_n" / "n.xmind", size=80, age_days=10)
    png = write_file(tmp_path / "notes" / "task_n" / "n.png", size=60, age_days=10)

    report = scan(repo, tmp_path, settings=policies)

    assert not md.exists() and not xm.exists() and not png.exists()
    assert report.freed_bytes == 240
    assert repo.tasks["task_n"].note_path is None
    assert repo.tasks["task_n"].mindmap_paths == []


def test_orphan_files_cleaned_when_task_not_in_db(tmp_path):
    """orphan 文件(任务记录已不存在)按年龄回收。"""
    repo = FakeRepo()  # 空 repo,任何 task_id 都查不到
    orphan = write_file(tmp_path / "videos" / "task_ghost" / "x.mp4", size=77, age_days=20)

    report = scan(repo, tmp_path)

    assert not orphan.exists()
    assert "videos/task_ghost/x.mp4" in report.deleted
    assert report.freed_bytes == 77


def test_not_expired_below_threshold_is_kept(tmp_path):
    """3 天龄的 7d 视频不应被删。"""
    repo = FakeRepo()
    repo.add(FakeTask("task_new", status="completed", video_path="videos/task_new/v.mp4"))
    video = write_file(tmp_path / "videos" / "task_new" / "v.mp4", size=10, age_days=3)

    report = scan(repo, tmp_path)

    assert video.exists()
    assert report.deleted == []


def test_empty_task_dir_removed_after_cleanup(tmp_path):
    """删除产物后空的任务子目录被清掉,保持产物目录整洁。"""
    repo = FakeRepo()
    repo.add(FakeTask("task_e", status="completed", video_path="videos/task_e/v.mp4"))
    write_file(tmp_path / "videos" / "task_e" / "v.mp4", size=5, age_days=10)

    scan(repo, tmp_path)

    assert not (tmp_path / "videos" / "task_e").exists()


# ---------------------------------------------------------------------------
# temp 目录清理
# ---------------------------------------------------------------------------


def test_temp_of_terminal_task_removed_and_active_kept(tmp_path):
    """终态任务的 temp 被清,活跃任务的 temp 保留。"""
    repo = FakeRepo()
    repo.add(FakeTask("task_done", status="completed"))
    repo.add(FakeTask("task_run", status="running"))
    done_temp = tmp_path / "temp" / "task_done"
    run_temp = tmp_path / "temp" / "task_run"
    write_file(done_temp / "part.bin", size=400, age_days=1)
    write_file(run_temp / "seg.bin", size=200, age_days=1)

    report = scan(repo, tmp_path)

    assert not done_temp.exists()
    assert run_temp.exists()
    assert report.freed_bytes == 400
    assert any(d.endswith("temp/task_done/") for d in report.deleted)
    assert report.skipped_active >= 1  # 活跃任务 temp 被跳过


def test_cleanup_task_temp_removes_specific_task(tmp_path):
    """cleanup_task_temp 清空指定任务的 temp。"""
    write_file(tmp_path / "temp" / "task_x" / "a.bin", size=10)
    write_file(tmp_path / "temp" / "task_y" / "b.bin", size=10)

    freed = cleanup_task_temp("task_x", data_root=tmp_path)

    assert freed == 10
    assert not (tmp_path / "temp" / "task_x").exists()
    assert (tmp_path / "temp" / "task_y").exists()  # 其它任务不受影响


def test_cleanup_task_temp_idempotent_when_missing(tmp_path):
    """temp 目录不存在时 cleanup_task_temp 不报错。"""
    assert cleanup_task_temp("nobody", data_root=tmp_path) == 0


# ---------------------------------------------------------------------------
# cleanup_expired 便捷入口
# ---------------------------------------------------------------------------


def test_cleanup_expired_wrapper_uses_injected_clock_and_repo(tmp_path):
    """cleanup_expired 接受 now/repo/data_root/settings 注入并委托扫描。"""
    repo = FakeRepo()
    repo.add(FakeTask("task_w", status="completed", video_path="videos/task_w/v.mp4"))
    write_file(tmp_path / "videos" / "task_w" / "v.mp4", size=999, age_days=8)

    report = cleanup_expired(now=NOW, repo=repo, data_root=tmp_path, settings=POLICIES)

    assert isinstance(report, CleanupReport)
    assert report.freed_bytes == 999
    assert repo.tasks["task_w"].video_path is None


# ---------------------------------------------------------------------------
# 存储统计(task 1.13)
# ---------------------------------------------------------------------------


def test_storage_stats_fields_and_breakdown(tmp_path):
    """统计字段齐全:总量 / 五类 / Top 任务 / 人类可读。"""
    write_file(tmp_path / "videos" / "task_a" / "a.mp4", size=1000)
    write_file(tmp_path / "audio" / "task_a" / "a.wav", size=500)
    write_file(tmp_path / "notes" / "task_b" / "n.md", size=200)
    write_file(tmp_path / "temp" / "task_a" / "junk.bin", size=300)

    stats = storage_stats(tmp_path)

    assert stats["total_bytes"] == 1700  # 仅产物,不含 temp
    assert stats["by_kind"] == {
        "video": 1000,
        "audio": 500,
        "srt": 0,
        "note": 200,
        "screenshot": 0,
    }
    assert stats["temp_bytes"] == 300
    # Top 任务(降序)
    assert stats["top_tasks"][0] == {
        "task_id": "task_a",
        "bytes": 1500,
        "bytes_human": format_bytes(1500),
    }
    assert stats["top_tasks"][1]["task_id"] == "task_b"
    assert stats["top_tasks"][1]["bytes"] == 200
    # 人类可读字段存在且为字符串
    assert isinstance(stats["total_human"], str)
    assert set(stats["by_kind_human"].keys()) == {
        "video", "audio", "srt", "note", "screenshot"
    }


def test_storage_stats_reflects_cleanup(tmp_path):
    """清理后用量下降幅度与被删文件大小一致(spec storage-retention 场景)。"""
    repo = FakeRepo()
    repo.add(
        FakeTask("task_c", status="completed", video_path="videos/task_c/v.mp4")
    )
    write_file(tmp_path / "videos" / "task_c" / "v.mp4", size=2000, age_days=8)
    write_file(tmp_path / "notes" / "task_c" / "keep.md", size=100)  # permanent 保留

    before = storage_stats(tmp_path)
    assert before["total_bytes"] == 2100

    report = scan(repo, tmp_path)
    assert report.freed_bytes == 2000

    after = storage_stats(tmp_path)
    assert after["total_bytes"] == 100  # 仅剩笔记
    assert after["by_kind"]["video"] == 0
    assert after["by_kind"]["note"] == 100
    # 下降幅度 == 删除文件大小
    assert before["total_bytes"] - after["total_bytes"] == report.freed_bytes


def test_format_bytes_human_readable():
    assert format_bytes(0) == "0 B"
    assert format_bytes(512) == "512 B"
    assert format_bytes(1024) == "1.0 KB"
    assert format_bytes(2048) == "2.0 KB"
    assert format_bytes(1024 * 1024) == "1.0 MB"
    assert "GB" in format_bytes(1024 ** 3)
    assert format_bytes(-5) == "0 B"
    assert format_bytes("not a number") == "0 B"


# ---------------------------------------------------------------------------
# 策略抽取 / 默认值
# ---------------------------------------------------------------------------


def test_default_policies_when_settings_none():
    """settings=None 时全部回退到默认(video/audio=7d、srt/screenshot=30d、note=permanent)。"""
    from src.retention.cleaner import _extract_policies

    policies = _extract_policies(None)
    assert policies == DEFAULT_RETENTION_POLICIES
    assert policies["note"] == RetentionPolicy.PERMANENT
    assert policies["video"] == RetentionPolicy.DAYS_7


def test_invalid_policy_value_falls_back_to_default():
    """非法策略值被收敛为默认(不在扫描层抛错)。"""
    from src.retention.cleaner import _extract_policies

    policies = _extract_policies({"retention.video": "3 天"})
    assert policies["video"] == DEFAULT_RETENTION_POLICIES["video"]
