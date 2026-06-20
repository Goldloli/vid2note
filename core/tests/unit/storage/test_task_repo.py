"""测试任务仓库"""

import pytest
from vid2note_core.storage.db import Database
from vid2note_core.storage.task_repo import TaskRepository
from vid2note_core.types import NodeStatus, TaskStatus


@pytest.fixture
def repo(tmp_path):
    Database.reset_instance()
    db = Database(str(tmp_path / "tasks.db"))
    yield TaskRepository(db)
    Database.reset_instance()


def test_create_task(repo):
    task = repo.create("task_abcdef012345", video_url="https://youtube.com/x")
    assert task.id == "task_abcdef012345"
    assert task.status == TaskStatus.PENDING


def test_reserve_pending_task(repo):
    repo.create("task_abc123456789", status=TaskStatus.PENDING)
    repo.create("task_def123456789", status=TaskStatus.PENDING)
    t1 = repo.reserve_pending_task()
    assert t1 is not None
    t2 = repo.reserve_pending_task()
    assert t2 is not None
    # 第三个没有了
    t3 = repo.reserve_pending_task()
    assert t3 is None


def test_reserve_pending_task_atomic(repo):
    """并发 reserve 只应成功一次"""
    repo.create("task_abc123456789", status=TaskStatus.PENDING)
    # 单线程模拟：reserve 后状态变 running
    t1 = repo.reserve_pending_task()
    assert t1.status == TaskStatus.RUNNING
    t2 = repo.reserve_pending_task()
    assert t2 is None


def test_update_node_status(repo):
    repo.create("task_abc123456789")
    repo.update_node("task_abc123456789", "download", NodeStatus.COMPLETED, artifacts=["video.mp4"])
    node = repo.get_node("task_abc123456789", "download")
    assert node.status == NodeStatus.COMPLETED
    assert node.artifacts == ["video.mp4"]


def test_list_tasks(repo):
    repo.create("task_abc123456789")
    repo.create("task_def123456789")
    tasks = repo.list_all(limit=10)
    assert len(tasks) == 2


def test_count_by_status(repo):
    repo.create("task_abc123456789", status=TaskStatus.PENDING)
    repo.create("task_def123456789", status=TaskStatus.COMPLETED)
    assert repo.count_by_status(TaskStatus.PENDING) == 1
    assert repo.count_by_status(TaskStatus.COMPLETED) == 1


def test_reads_retry_and_structured_error_fields(repo):
    task_id = "task_abcdef012345"
    repo.create(task_id, status=TaskStatus.PENDING)
    repo.update(
        task_id,
        retry_count=2,
        error_code="DOWNLOAD_TIMEOUT",
        error_retryable=True,
    )

    task = repo.get_by_id(task_id)

    assert task.retry_count == 2
    assert task.error_code == "DOWNLOAD_TIMEOUT"
    assert task.error_retryable is True
