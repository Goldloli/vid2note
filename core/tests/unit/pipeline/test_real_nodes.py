"""
真实 pipeline 节点测试（mock 掉下载器/ffmpeg/ASR/LLM 外部依赖）。

验证 artifact-driven 流转：
  download → extract_audio → transcribe → organize → mindmap
每节点从 ArtifactStore 读取上游产物、产出落盘、返回 NodeResult。
"""

from unittest.mock import MagicMock

import pytest
from vid2note_core.asr.base import ASRResult, ASRSegment
from vid2note_core.downloaders.base import DownloadResult
from vid2note_core.events.bus import get_event_bus
from vid2note_core.pipeline.context import TaskContext
from vid2note_core.pipeline.real_nodes import (
    RealCleanupNode,
    RealDownloadNode,
    RealExtractAudioNode,
    RealMindmapNode,
    RealOrganizeNode,
    RealProposeWikiChangesNode,
    RealRegisterSourceNode,
    RealTranscribeNode,
    _asr_result_to_srt,
    _clean_mindmap_output,
    _format_timestamp,
)
from vid2note_core.source.registrar import SourceRegistrar
from vid2note_core.storage.artifact_store import ArtifactStore
from vid2note_core.storage.db import Database
from vid2note_core.storage.task_repo import TaskRecord
from vid2note_core.types import NodeName, NodeStatus, TaskId, TaskStatus
from vid2note_core.vault.layout import VaultLayout
from vid2note_core.vault.repository import VaultRepository
from vid2note_core.wiki.store import ChangeSetStore


@pytest.fixture
def store(tmp_path):
    return ArtifactStore(base_dir=tmp_path)


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    """每个测试用独立 SQLite，避免全局单例污染。节点都显式传入 store=tmp_path。"""
    Database.reset_instance()
    Database(str(tmp_path / "tasks.db"))
    yield
    Database.reset_instance()


# ── DownloadNode ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_download_node_success(store):
    fake_router = MagicMock()
    fake_router.download_with_fallback.return_value = DownloadResult(
        video_path=store.base_dir / "src.mp4", metadata={"title": "demo"}
    )
    # 准备一个假视频文件
    (store.base_dir / "src.mp4").write_bytes(b"FAKEVIDEO")

    node = RealDownloadNode(router=fake_router, store=store)
    ctx = TaskContext(task_id=TaskId("task_abcdef012345"), config={"url": "https://x.com/v"})

    result = await node.run(ctx)

    assert result.status == NodeStatus.COMPLETED
    fake_router.download_with_fallback.assert_called_once()
    # 产物落盘
    assert store.exists("task_abcdef012345", NodeName.DOWNLOAD.value, "video_file")
    assert (
        store.read_artifact("task_abcdef012345", NodeName.DOWNLOAD.value, "video_file")
        == b"FAKEVIDEO"
    )


@pytest.mark.asyncio
async def test_download_node_missing_url(store):
    node = RealDownloadNode(router=MagicMock(), store=store)
    ctx = TaskContext(task_id=TaskId("task_abcdef012345"), config={})
    result = await node.run(ctx)
    assert result.status == NodeStatus.FAILED
    assert result.error["code"] == "DOWNLOAD_URL_INVALID"


@pytest.mark.asyncio
async def test_download_node_downloader_failure(store):
    fake_router = MagicMock()
    fake_router.download_with_fallback.side_effect = RuntimeError("network down")
    node = RealDownloadNode(router=fake_router, store=store)
    ctx = TaskContext(task_id=TaskId("task_abcdef012345"), config={"url": "https://x.com/v"})
    result = await node.run(ctx)
    assert result.status == NodeStatus.FAILED
    assert result.error["code"] == "DOWNLOAD_ERROR"


# ── ExtractAudioNode ────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_audio_node_success(store):
    # 上游产物
    store.write_artifact("task_abcdef012345", NodeName.DOWNLOAD.value, "video_file", b"FAKEVIDEO")
    fake_extractor = MagicMock()
    fake_extractor.extract.return_value = store.base_dir / "audio.wav"
    (store.base_dir / "audio.wav").write_bytes(b"WAVDATA")

    node = RealExtractAudioNode(extractor=fake_extractor, store=store)
    ctx = TaskContext(task_id=TaskId("task_abcdef012345"))
    result = await node.run(ctx)

    assert result.status == NodeStatus.COMPLETED
    assert store.exists("task_abcdef012345", NodeName.EXTRACT_AUDIO.value, "audio_file")
    assert (
        store.read_artifact("task_abcdef012345", NodeName.EXTRACT_AUDIO.value, "audio_file")
        == b"WAVDATA"
    )


@pytest.mark.asyncio
async def test_extract_audio_node_ffmpeg_failure(store):
    store.write_artifact("task_abcdef012345", NodeName.DOWNLOAD.value, "video_file", b"FAKEVIDEO")
    fake_extractor = MagicMock()
    fake_extractor.extract.side_effect = RuntimeError("ffmpeg broken")
    node = RealExtractAudioNode(extractor=fake_extractor, store=store)
    ctx = TaskContext(task_id=TaskId("task_abcdef012345"))
    result = await node.run(ctx)
    assert result.status == NodeStatus.FAILED
    assert result.error["code"] == "AUDIO_EXTRACT_FAILED"


@pytest.mark.asyncio
async def test_register_source_node_writes_vault_source(store, tmp_path):
    task_id = "task_abcdef012345"
    store.write_artifact(
        task_id,
        NodeName.TRANSCRIBE.value,
        "srt_file",
        b"1\n00:00:01,000 --> 00:00:03,000\nEvidence.\n",
    )
    store.write_artifact(
        task_id,
        NodeName.ORGANIZE.value,
        "markdown_file",
        b"# Summary\n",
    )
    repository = MagicMock()
    repository.get_by_id.return_value = TaskRecord(
        id=task_id,
        status=TaskStatus.RUNNING,
        video_url="https://example.com/watch?v=1",
    )
    registrar = SourceRegistrar(VaultLayout.initialize(tmp_path / "vault"))
    node = RealRegisterSourceNode(registrar=registrar, store=store, repository=repository)

    result = await node.run(TaskContext(task_id=TaskId(task_id)))

    assert result.status == NodeStatus.COMPLETED
    assert list(registrar.layout.raw.glob("*/source.yaml"))
    assert store.exists(task_id, NodeName.REGISTER_SOURCE.value, "source_record")


@pytest.mark.asyncio
async def test_register_then_mindmap_progress_never_moves_backwards(store, tmp_path):
    task_id = "task_abcdef012345"
    store.write_artifact(
        task_id,
        NodeName.TRANSCRIBE.value,
        "srt_file",
        b"1\n00:00:00,000 --> 00:00:01,000\nEvidence.\n",
    )
    store.write_artifact(task_id, NodeName.ORGANIZE.value, "markdown_file", b"# Summary\n")
    repository = MagicMock()
    repository.get_by_id.return_value = TaskRecord(
        id=task_id,
        status=TaskStatus.RUNNING,
        video_url="https://example.com/watch?v=1",
    )
    registrar = SourceRegistrar(VaultLayout.initialize(tmp_path / "vault"))
    register = RealRegisterSourceNode(registrar=registrar, store=store, repository=repository)
    llm = MagicMock()
    llm.chat.return_value = "mindmap\n  root((Summary))"
    mindmap = RealMindmapNode(llm=llm, store=store)
    queue = get_event_bus().subscribe(task_id)

    try:
        await register.run(TaskContext(task_id=TaskId(task_id)))
        await mindmap.run(TaskContext(task_id=TaskId(task_id)))
        progress = [queue.get_nowait().progress for _ in range(queue.qsize())]
    finally:
        get_event_bus().unsubscribe(task_id, queue)

    assert progress == sorted(progress)


@pytest.mark.asyncio
async def test_propose_wiki_changes_node_saves_pending_changeset(store, tmp_path):
    import json
    from datetime import UTC, datetime

    from vid2note_core.source.registrar import SourceRegistration

    task_id = "task_abcdef012345"
    layout = VaultLayout.initialize(tmp_path / "vault")
    srt = tmp_path / "source.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nEvidence.\n", encoding="utf-8")
    note = tmp_path / "note.md"
    note.write_text("# Evidence\n", encoding="utf-8")
    record = SourceRegistrar(layout).register(
        SourceRegistration(
            task_id=task_id,
            canonical_url="https://example.com/wiki",
            title="Wiki evidence",
            imported_at=datetime(2026, 6, 19, tzinfo=UTC),
            srt_path=srt,
            note_path=note,
        )
    )
    store.write_artifact(
        task_id,
        NodeName.REGISTER_SOURCE.value,
        "source_record",
        record.model_dump_json().encode(),
    )
    response = {
        "classification": "new",
        "changeset": {
            "id": "chg_abcdef012345",
            "created_at": "2026-06-19T00:00:00Z",
            "source_ids": [record.source_id],
            "base_revision": "initial",
            "agent_runtime": "built-in",
            "summary": "Create Wiki evidence",
            "operations": [
                {
                    "page_id": "concept_wiki_evidence",
                    "path": "wiki/concepts/wiki-evidence.md",
                    "action": "create",
                    "after": "# Wiki evidence\n",
                    "rationale": "New source",
                    "citations": [
                        {"source_id": record.source_id, "start_ms": 1000, "end_ms": 3000}
                    ],
                }
            ],
            "contradictions": [],
        },
    }
    llm = MagicMock()
    llm.chat.return_value = json.dumps(response)
    changesets = ChangeSetStore(layout.root)
    node = RealProposeWikiChangesNode(
        llm=llm,
        store=store,
        vault=VaultRepository(layout),
        changesets=changesets,
    )

    result = await node.run(TaskContext(task_id=TaskId(task_id)))

    assert result.status == NodeStatus.COMPLETED
    assert changesets.get("chg_abcdef012345") is not None
    assert result.metadata["changeset_id"] == "chg_abcdef012345"


# ── TranscribeNode ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_transcribe_node_success(store):
    store.write_artifact(
        "task_abcdef012345", NodeName.EXTRACT_AUDIO.value, "audio_file", b"WAVDATA"
    )
    fake_asr = MagicMock()
    fake_asr.transcribe.return_value = ASRResult(
        text_full="你好世界",
        segments=[
            ASRSegment(start_ms=0, end_ms=1500, text="你好"),
            ASRSegment(start_ms=1500, end_ms=3000, text="世界"),
        ],
        language="zh",
    )
    node = RealTranscribeNode(asr=fake_asr, store=store)
    ctx = TaskContext(task_id=TaskId("task_abcdef012345"), config={"language": "zh"})
    result = await node.run(ctx)

    assert result.status == NodeStatus.COMPLETED
    srt = store.read_artifact("task_abcdef012345", NodeName.TRANSCRIBE.value, "srt_file").decode(
        "utf-8"
    )
    assert "你好" in srt and "世界" in srt
    assert "00:00:00,000 --> 00:00:01,500" in srt


@pytest.mark.asyncio
async def test_transcribe_node_supports_async_asr(store):
    store.write_artifact(
        "task_abcdef012345", NodeName.EXTRACT_AUDIO.value, "audio_file", b"WAVDATA"
    )
    fake_asr = MagicMock()

    async def _async_transcribe(audio_path, opts):
        return ASRResult(text_full="async", segments=[], language="zh")

    fake_asr.transcribe.side_effect = _async_transcribe
    node = RealTranscribeNode(asr=fake_asr, store=store)
    ctx = TaskContext(task_id=TaskId("task_abcdef012345"))
    result = await node.run(ctx)
    assert result.status == NodeStatus.COMPLETED


@pytest.mark.asyncio
async def test_transcribe_node_asr_failure(store):
    store.write_artifact(
        "task_abcdef012345", NodeName.EXTRACT_AUDIO.value, "audio_file", b"WAVDATA"
    )
    fake_asr = MagicMock()
    fake_asr.transcribe.side_effect = RuntimeError("asr down")
    node = RealTranscribeNode(asr=fake_asr, store=store)
    ctx = TaskContext(task_id=TaskId("task_abcdef012345"))
    result = await node.run(ctx)
    assert result.status == NodeStatus.FAILED
    assert result.error["code"] == "ASR_ERROR"


# ── OrganizeNode ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_organize_node_success(store):
    store.write_artifact(
        "task_abcdef012345",
        NodeName.TRANSCRIBE.value,
        "srt_file",
        "1\n00:00:00,000 --> 00:00:01,000\n你好\n".encode(),
    )
    fake_llm = MagicMock()
    fake_llm.restructure_content.return_value = "# 笔记\n\n要点"
    node = RealOrganizeNode(llm=fake_llm, store=store)
    ctx = TaskContext(task_id=TaskId("task_abcdef012345"))
    result = await node.run(ctx)

    assert result.status == NodeStatus.COMPLETED
    md = store.read_artifact("task_abcdef012345", NodeName.ORGANIZE.value, "markdown_file").decode(
        "utf-8"
    )
    assert md == "# 笔记\n\n要点"
    fake_llm.restructure_content.assert_called_once()


@pytest.mark.asyncio
async def test_organize_node_llm_failure(store):
    store.write_artifact("task_abcdef012345", NodeName.TRANSCRIBE.value, "srt_file", b"x")
    fake_llm = MagicMock()
    fake_llm.restructure_content.side_effect = RuntimeError("llm timeout")
    node = RealOrganizeNode(llm=fake_llm, store=store)
    ctx = TaskContext(task_id=TaskId("task_abcdef012345"))
    result = await node.run(ctx)
    assert result.status == NodeStatus.FAILED
    assert result.error["code"] == "LLM_ERROR"


# ── MindmapNode ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mindmap_node_success(store):
    """思维导图节点读取 markdown_file、调 LLM、落盘 mermaid"""
    store.write_artifact(
        "task_abcdef012345",
        NodeName.ORGANIZE.value,
        "markdown_file",
        "# 笔记\n\n- 要点".encode(),
    )
    fake_llm = MagicMock()
    fake_llm.chat.return_value = "mindmap\n  root((主题))\n    要点"
    node = RealMindmapNode(llm=fake_llm, store=store)
    ctx = TaskContext(task_id=TaskId("task_abcdef012345"))
    result = await node.run(ctx)

    assert result.status == NodeStatus.COMPLETED
    assert store.exists("task_abcdef012345", NodeName.MINDMAP.value, "mindmap_file")
    mm = store.read_artifact("task_abcdef012345", NodeName.MINDMAP.value, "mindmap_file").decode(
        "utf-8"
    )
    assert "mindmap" in mm
    assert "主题" in mm
    # 验证 LLM 被调用，且 prompt 来自 mindmap.txt（含 markdown_content）
    fake_llm.chat.assert_called_once()
    user_msg = fake_llm.chat.call_args.args[0][1]["content"]
    assert "# 笔记" in user_msg  # 上游 markdown 被填入 prompt


@pytest.mark.asyncio
async def test_mindmap_node_strips_code_fence(store):
    """LLM 即便包裹了 ```mermaid 代码块，也应被剥离"""
    store.write_artifact(
        "task_abcdef012345",
        NodeName.ORGANIZE.value,
        "markdown_file",
        "# 笔记".encode(),
    )
    fake_llm = MagicMock()
    fake_llm.chat.return_value = "```mermaid\nmindmap\n  root((T))\n```"
    node = RealMindmapNode(llm=fake_llm, store=store)
    ctx = TaskContext(task_id=TaskId("task_abcdef012345"))
    result = await node.run(ctx)
    assert result.status == NodeStatus.COMPLETED
    mm = store.read_artifact("task_abcdef012345", NodeName.MINDMAP.value, "mindmap_file").decode(
        "utf-8"
    )
    assert not mm.startswith("```")
    assert "mindmap" in mm


@pytest.mark.asyncio
async def test_mindmap_node_llm_failure(store):
    store.write_artifact(
        "task_abcdef012345",
        NodeName.ORGANIZE.value,
        "markdown_file",
        "# 笔记".encode(),
    )
    fake_llm = MagicMock()
    fake_llm.chat.side_effect = RuntimeError("llm down")
    node = RealMindmapNode(llm=fake_llm, store=store)
    ctx = TaskContext(task_id=TaskId("task_abcdef012345"))
    result = await node.run(ctx)
    assert result.status == NodeStatus.FAILED
    assert result.error["code"] == "LLM_ERROR"


@pytest.mark.asyncio
async def test_mindmap_node_outline_format(store):
    """format=outline 应使用 mindmap_outline.txt 模板（{content} 占位）"""
    store.write_artifact(
        "task_abcdef012345",
        NodeName.ORGANIZE.value,
        "markdown_file",
        "# 笔记".encode(),
    )
    fake_llm = MagicMock()
    fake_llm.chat.return_value = "课程主题\n  第一章"
    node = RealMindmapNode(llm=fake_llm, store=store, mindmap_format="outline")
    ctx = TaskContext(task_id=TaskId("task_abcdef012345"))
    result = await node.run(ctx)
    assert result.status == NodeStatus.COMPLETED
    user_msg = fake_llm.chat.call_args.args[0][1]["content"]
    # outline 模板含"层级结构分析师"字样
    assert "结构分析" in user_msg
    assert "# 笔记" in user_msg
    assert result.metadata["format"] == "outline"


def test_clean_mindmap_output_plain():
    assert _clean_mindmap_output("mindmap\n  root", "mermaid") == "mindmap\n  root"


def test_clean_mindmap_output_mermaid_fence():
    out = _clean_mindmap_output("```mermaid\nmindmap\n  root((T))\n```", "mermaid")
    assert out == "mindmap\n  root((T))"


def test_clean_mindmap_output_bare_fence():
    out = _clean_mindmap_output("```\nmindmap\n  root\n```", "mermaid")
    assert out == "mindmap\n  root"


def test_clean_mindmap_output_empty():
    assert _clean_mindmap_output("", "mermaid") == ""


# ── CleanupNode ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cleanup_deletes_video_and_audio_default(store):
    """默认策略：删除 video + audio，保留 srt/markdown/mindmap"""
    store.write_artifact("task_abcdef012345", NodeName.DOWNLOAD.value, "video_file", b"VIDEO")
    store.write_artifact("task_abcdef012345", NodeName.EXTRACT_AUDIO.value, "audio_file", b"AUDIO")
    store.write_artifact("task_abcdef012345", NodeName.TRANSCRIBE.value, "srt_file", b"SRT")
    store.write_artifact("task_abcdef012345", NodeName.ORGANIZE.value, "markdown_file", b"MD")

    node = RealCleanupNode(store=store)
    ctx = TaskContext(task_id=TaskId("task_abcdef012345"))
    result = await node.run(ctx)

    assert result.status == NodeStatus.COMPLETED
    assert not store.exists("task_abcdef012345", NodeName.DOWNLOAD.value, "video_file")
    assert not store.exists("task_abcdef012345", NodeName.EXTRACT_AUDIO.value, "audio_file")
    # 保留 srt/markdown
    assert store.exists("task_abcdef012345", NodeName.TRANSCRIBE.value, "srt_file")
    assert store.exists("task_abcdef012345", NodeName.ORGANIZE.value, "markdown_file")
    # 删除清单落盘
    assert store.exists("task_abcdef012345", NodeName.CLEANUP.value, "cleanup_manifest")


@pytest.mark.asyncio
async def test_cleanup_manifest_content(store):
    """删除清单内容正确"""
    import json

    store.write_artifact("task_abcdef012345", NodeName.DOWNLOAD.value, "video_file", b"V")
    store.write_artifact("task_abcdef012345", NodeName.EXTRACT_AUDIO.value, "audio_file", b"A")

    node = RealCleanupNode(store=store)
    ctx = TaskContext(task_id=TaskId("task_abcdef012345"))
    await node.run(ctx)

    manifest_raw = store.read_artifact(
        "task_abcdef012345", NodeName.CLEANUP.value, "cleanup_manifest"
    )
    manifest = json.loads(manifest_raw)
    assert "video_file" in manifest["deleted"]
    assert "audio_file" in manifest["deleted"]
    assert "srt" in manifest["kept"]
    assert "markdown" in manifest["kept"]
    assert manifest["keep_video"] is False
    assert manifest["keep_audio"] is False


@pytest.mark.asyncio
async def test_cleanup_keep_video_override(store):
    """keep_video=True 时保留 video，只删 audio"""
    store.write_artifact("task_abcdef012345", NodeName.DOWNLOAD.value, "video_file", b"V")
    store.write_artifact("task_abcdef012345", NodeName.EXTRACT_AUDIO.value, "audio_file", b"A")

    node = RealCleanupNode(store=store)
    ctx = TaskContext(task_id=TaskId("task_abcdef012345"), config={"keep_video": True})
    result = await node.run(ctx)

    assert result.status == NodeStatus.COMPLETED
    assert store.exists("task_abcdef012345", NodeName.DOWNLOAD.value, "video_file")
    assert not store.exists("task_abcdef012345", NodeName.EXTRACT_AUDIO.value, "audio_file")


@pytest.mark.asyncio
async def test_cleanup_keep_audio_override(store):
    """keep_audio=True 时保留 audio，只删 video"""
    store.write_artifact("task_abcdef012345", NodeName.DOWNLOAD.value, "video_file", b"V")
    store.write_artifact("task_abcdef012345", NodeName.EXTRACT_AUDIO.value, "audio_file", b"A")

    node = RealCleanupNode(store=store)
    ctx = TaskContext(task_id=TaskId("task_abcdef012345"), config={"keep_audio": True})
    await node.run(ctx)

    assert not store.exists("task_abcdef012345", NodeName.DOWNLOAD.value, "video_file")
    assert store.exists("task_abcdef012345", NodeName.EXTRACT_AUDIO.value, "audio_file")


@pytest.mark.asyncio
async def test_cleanup_noop_when_nothing_to_delete(store):
    """无 video/audio 产物时仍成功，清单记录 deleted 为空"""
    node = RealCleanupNode(store=store)
    ctx = TaskContext(task_id=TaskId("task_abcdef012345"))
    result = await node.run(ctx)

    assert result.status == NodeStatus.COMPLETED
    import json

    manifest = json.loads(
        store.read_artifact("task_abcdef012345", NodeName.CLEANUP.value, "cleanup_manifest")
    )
    assert manifest["deleted"] == []


# ── 默认 provider 失败应显式抛错（不再静默回退 mock） ──────────


def test_default_asr_invalid_provider_raises():
    """asr_provider 错误时应抛 ASRError 而非回退 mock。"""
    from vid2note_core.errors import ASRError
    from vid2note_core.pipeline.real_nodes import _default_asr

    with pytest.raises(ASRError, match="不支持的 ASR 提供商"):
        _default_asr({"asr_provider": "nonexistent_provider"})


def test_default_llm_missing_key_raises():
    """api_key 缺失时应抛 LLMError 而非回退 MockLLM。"""
    from vid2note_core.errors import LLMError
    from vid2note_core.pipeline.real_nodes import _default_llm

    with pytest.raises(LLMError, match="缺少 API Key"):
        _default_llm({"llm_provider": "qwen", "api_key": ""})


# ── 辅助函数 ────────────────────────────────────────────────


def test_format_timestamp():
    assert _format_timestamp(0) == "00:00:00,000"
    assert _format_timestamp(1500) == "00:00:01,500"
    assert _format_timestamp(3_661_000) == "01:01:01,000"
    assert _format_timestamp(-5) == "00:00:00,000"


def test_asr_result_to_srt_with_segments():
    result = ASRResult(
        text_full="ab",
        segments=[
            ASRSegment(start_ms=0, end_ms=1000, text="a"),
            ASRSegment(start_ms=1000, end_ms=2000, text="b"),
        ],
    )
    srt = _asr_result_to_srt(result)
    assert srt.count("\n") >= 5
    assert "00:00:00,000 --> 00:00:01,000" in srt
    assert "00:00:01,000 --> 00:00:02,000" in srt


def test_asr_result_to_srt_empty():
    result = ASRResult(text_full="纯文本", segments=[])
    srt = _asr_result_to_srt(result)
    assert "纯文本" in srt
