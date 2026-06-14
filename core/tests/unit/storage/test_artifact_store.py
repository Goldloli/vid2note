"""测试产物存储"""
from pathlib import Path
from vid2note_core.storage.artifact_store import ArtifactStore


def test_ensure_task_dir(tmp_path):
    store = ArtifactStore(base_dir=tmp_path)
    d = store.ensure_task_dir("task_abc123456789")
    assert d.exists()
    assert (d / "artifacts").exists()
    assert (d / "logs").exists()


def test_write_and_read_artifact(tmp_path):
    store = ArtifactStore(base_dir=tmp_path)
    store.write_artifact("task_abc123456789", "download", "video.mp4", b"fake video")
    data = store.read_artifact("task_abc123456789", "download", "video.mp4")
    assert data == b"fake video"


def test_artifact_path(tmp_path):
    store = ArtifactStore(base_dir=tmp_path)
    p = store.artifact_path("task_abc123456789", "download", "video.mp4")
    assert "download_video.mp4" in str(p)
    assert "task_abc123456789" in str(p)


def test_delete_artifact(tmp_path):
    store = ArtifactStore(base_dir=tmp_path)
    store.write_artifact("task_abc123456789", "download", "video.mp4", b"x")
    store.delete_artifact("task_abc123456789", "download", "video.mp4")
    assert not store.artifact_path("task_abc123456789", "download", "video.mp4").exists()


def test_delete_downstream_artifacts(tmp_path):
    store = ArtifactStore(base_dir=tmp_path)
    store.write_artifact("task_abc123456789", "download", "video.mp4", b"x")
    store.write_artifact("task_abc123456789", "extract_audio", "audio.wav", b"x")
    store.write_artifact("task_abc123456789", "transcribe", "subtitle.srt", b"x")
    store.delete_downstream("task_abc123456789", "extract_audio")
    # extract_audio 和下游（transcribe）应被删，download 保留
    assert store.artifact_path("task_abc123456789", "download", "video.mp4").exists()
    assert not store.artifact_path("task_abc123456789", "extract_audio", "audio.wav").exists()
    assert not store.artifact_path("task_abc123456789", "transcribe", "subtitle.srt").exists()
