"""
TaskWorker 端到端测试：注入真实节点（mock 掉下载器/ffmpeg/ASR/LLM），
验证完整链路 download → extract_audio → transcribe → organize 的 artifact 流转。
"""

from unittest.mock import MagicMock

import pytest
from vid2note_core.asr.base import ASRResult, ASRSegment
from vid2note_core.downloaders.base import DownloadResult
from vid2note_core.pipeline.real_nodes import (
    RealDownloadNode,
    RealExtractAudioNode,
    RealOrganizeNode,
    RealTranscribeNode,
)
from vid2note_core.storage.artifact_store import ArtifactStore
from vid2note_core.storage.db import Database
from vid2note_core.storage.task_repo import TaskRepository
from vid2note_core.types import NodeName, TaskId, TaskStatus
from vid2note_core.worker import TaskWorker


@pytest.fixture
def env(tmp_path):
    """隔离 DB 到 tmp_path。节点显式传入 store=ArtifactStore(base_dir=tmp_path)。"""
    Database.reset_instance()
    Database(str(tmp_path / "tasks.db"))
    yield tmp_path
    Database.reset_instance()


def _build_nodes(store: ArtifactStore):
    """构建真实节点链路，所有外部依赖用 MagicMock。"""
    fake_router = MagicMock()
    fake_router.download_with_fallback.return_value = DownloadResult(
        video_path=store.base_dir / "v.mp4", metadata={"title": "demo"}
    )
    (store.base_dir / "v.mp4").write_bytes(b"FAKEVIDEO")

    fake_extractor = MagicMock()
    fake_extractor.extract.return_value = store.base_dir / "a.wav"
    (store.base_dir / "a.wav").write_bytes(b"WAVDATA")

    fake_asr = MagicMock()
    fake_asr.transcribe.return_value = ASRResult(
        text_full="你好世界",
        segments=[ASRSegment(0, 1500, "你好"), ASRSegment(1500, 3000, "世界")],
        language="zh",
    )

    fake_llm = MagicMock()
    fake_llm.restructure_content.return_value = "# 笔记\n\n- 要点"
    fake_llm.chat.return_value = "mindmap\n  root((主题))\n    要点"

    from vid2note_core.pipeline.real_nodes import RealCleanupNode, RealMindmapNode

    return [
        RealDownloadNode(router=fake_router, store=store),
        RealExtractAudioNode(extractor=fake_extractor, store=store),
        RealTranscribeNode(asr=fake_asr, store=store),
        RealOrganizeNode(llm=fake_llm, store=store),
        RealMindmapNode(llm=fake_llm, store=store),
        RealCleanupNode(store=store),
    ]


@pytest.mark.asyncio
async def test_worker_runs_full_pipeline(env):
    store = ArtifactStore(base_dir=env)

    repo = TaskRepository()
    task_id = TaskId.generate()
    repo.create(task_id=task_id, video_url="https://example.com/v", status=TaskStatus.PENDING)

    worker = TaskWorker(poll_interval=0.05, max_concurrent=1, nodes=_build_nodes(store))
    try:
        await worker.start()
        # 轮询并处理一个任务
        for _ in range(50):
            record = repo.get_by_id(task_id)
            if record and record.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                break
            await __import__("asyncio").sleep(0.05)
    finally:
        await worker.stop()

    record = repo.get_by_id(task_id)
    assert record is not None
    assert record.status == TaskStatus.COMPLETED, (
        f"实际状态: {record.status} {record.error_message}"
    )

    # 验证保留下来的产物（srt/markdown/mindmap）落盘
    assert store.exists(task_id, NodeName.TRANSCRIBE.value, "srt_file")
    assert store.exists(task_id, NodeName.ORGANIZE.value, "markdown_file")
    assert store.exists(task_id, NodeName.MINDMAP.value, "mindmap_file")
    srt = store.read_artifact(task_id, NodeName.TRANSCRIBE.value, "srt_file").decode("utf-8")
    assert "你好" in srt and "世界" in srt
    md = store.read_artifact(task_id, NodeName.ORGANIZE.value, "markdown_file").decode("utf-8")
    assert "# 笔记" in md
    mm = store.read_artifact(task_id, NodeName.MINDMAP.value, "mindmap_file").decode("utf-8")
    assert "mindmap" in mm and "主题" in mm
    # cleanup 节点已运行：默认删除 video/audio，保留 srt/markdown/mindmap，落盘删除清单
    assert not store.exists(task_id, NodeName.DOWNLOAD.value, "video_file")
    assert not store.exists(task_id, NodeName.EXTRACT_AUDIO.value, "audio_file")
    assert store.exists(task_id, NodeName.CLEANUP.value, "cleanup_manifest")
