"""测试类型定义"""
from pathlib import Path
from vid2note_core.types import TaskId, ArtifactRef, NodeName, NodeStatus, NodeResult, TaskStatus, RunMode


def test_task_id_creation():
    tid = TaskId("task_abcdef012345")
    assert tid.value == "task_abcdef012345"


def test_task_id_validation_valid():
    assert TaskId.is_valid("task_abcdef012345") is True


def test_task_id_validation_invalid_traversal():
    assert TaskId.is_valid("../../etc/passwd") is False


def test_task_id_validation_invalid_short():
    assert TaskId.is_valid("task_abc") is False


def test_artifact_ref():
    ref = ArtifactRef(node=NodeName.DOWNLOAD, name="video.mp4")
    assert ref.node == "download"
    assert ref.name == "video.mp4"


def test_node_result_success():
    r = NodeResult.success(
        node=NodeName.DOWNLOAD,
        artifacts=[ArtifactRef(NodeName.DOWNLOAD, "video.mp4")],
        metadata={"duration_sec": 60.0},
    )
    assert r.status == NodeStatus.COMPLETED
    assert r.error is None


def test_node_result_failure():
    r = NodeResult.failure(
        node=NodeName.DOWNLOAD,
        error_code="DOWNLOAD_NETWORK_ERROR",
        error_message="timeout",
    )
    assert r.status == NodeStatus.FAILED
    assert r.artifacts == []


def test_run_mode_values():
    assert RunMode.ELECTRON == "electron"
    assert RunMode.DOCKER == "docker"
    assert RunMode.CLI == "cli"
    assert RunMode.DEV == "dev"


def test_task_status_values():
    assert TaskStatus.PENDING == "pending"
    assert TaskStatus.RUNNING == "running"
    assert TaskStatus.COMPLETED == "completed"
    assert TaskStatus.FAILED == "failed"
    assert TaskStatus.CANCELLED == "cancelled"
    assert TaskStatus.PARTIAL == "partial"
