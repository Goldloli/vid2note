"""
Real pipeline nodes for vid2note.

与 nodes.py 里的 stub 节点不同，这些节点真正调用下载器/ffmpeg/ASR/LLM，
并通过 ArtifactStore 把产物落盘，遵循 artifact-driven 设计：
  - 每个节点从上游 artifact 读取输入（download 节点从 ctx.config 读 url/路径）
  - 调用真实模块完成工作
  - 把产物写入 ArtifactStore 并返回 ArtifactRef
  - 通过 EventBus 发布进度事件
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vid2note_core.audio.extractor import AudioExtractor
from vid2note_core.downloaders.base import DownloadOpts
from vid2note_core.downloaders.bili import BiliDownloader
from vid2note_core.downloaders.direct import DirectDownloader
from vid2note_core.downloaders.local_file import LocalFileDownloader
from vid2note_core.downloaders.router import DownloaderRouter
from vid2note_core.downloaders.ytdlp import YtdlpDownloader
from vid2note_core.errors import ASRError, LLMError, Vid2NoteError
from vid2note_core.events.bus import TaskEvent, get_event_bus
from vid2note_core.pipeline.context import TaskContext
from vid2note_core.pipeline.node import PipelineNode
from vid2note_core.source.registrar import SourceRegistrar, SourceRegistration
from vid2note_core.storage.artifact_store import ArtifactStore
from vid2note_core.types import ArtifactRef, NodeName, NodeResult, NodeStatus
from vid2note_core.vault.repository import VaultRepository
from vid2note_core.wiki.applier import ChangeSetApplier
from vid2note_core.wiki.compiler import CompileInput, WikiCompiler
from vid2note_core.wiki.policy import AutonomyMode, AutonomyPolicy
from vid2note_core.wiki.retrieval import WikiRetriever
from vid2note_core.wiki.store import ChangeSetStore


def _build_default_router() -> DownloaderRouter:
    """按设计稿路由策略装配下载器（顺序即优先级）。

    BiliDownloader 是纯 Python 实现（wbi 签名 + DASH 流 + ffmpeg 混流），
    无需 BBDown 二进制。YtdlpDownloader 保留为 fallback（YouTube + bilibili 兜底）。
    """
    return DownloaderRouter(
        [
            LocalFileDownloader(),
            DirectDownloader(),
            BiliDownloader(),
            YtdlpDownloader(),
        ]
    )


class _RealNodeMixin:
    """真实节点共享的事件发布与 DB 更新逻辑。"""

    name: NodeName

    async def _publish(
        self,
        task_id: str,
        event_type: str,
        progress: int,
        message: str,
        artifact: str | None = None,
    ) -> None:
        bus = get_event_bus()
        is_start = event_type == "node.started"
        bus.publish(
            TaskEvent(
                task_id=task_id,
                event_type=event_type,
                node_name=self.name.value,
                node_status=NodeStatus.RUNNING.value if is_start else NodeStatus.COMPLETED.value,
                progress=progress,
                message=message,
                artifact=artifact,
                timestamp=datetime.now().isoformat(),
            )
        )

    def _update_db(
        self,
        task_id: str,
        status: NodeStatus,
        artifacts: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        error: dict[str, str] | None = None,
    ) -> None:
        repository = getattr(self, "repository", None)
        if repository is None:
            return
        repository.update_node(
            task_id,
            self.name.value,
            status,
            artifacts=artifacts or [],
            metadata=metadata or {},
            error=error,
        )


class RealDownloadNode(PipelineNode, _RealNodeMixin):
    """下载视频：url/路径 → video_file。"""

    name = NodeName.DOWNLOAD
    requires: list[str] = []
    produces: list[str] = ["video_file"]

    def __init__(self, router=None, store: ArtifactStore | None = None, repository=None):
        self.router = router or _build_default_router()
        if store is None:
            raise TypeError("store is required")
        self.store = store
        self.repository = repository

    async def run(self, ctx: TaskContext) -> NodeResult:
        task_id = ctx.task_id.value
        url = ctx.config.get("url") or ctx.config.get("video_url")
        if not url:
            return NodeResult.failure(self.name, "DOWNLOAD_URL_INVALID", "缺少 url/video_url 配置")

        task_dir = self.store.ensure_task_dir(task_id)
        dest_dir = task_dir / "artifacts"
        dest_dir.mkdir(parents=True, exist_ok=True)
        opts = DownloadOpts(
            cookie_path=Path(ctx.config["cookie_path"]) if ctx.config.get("cookie_path") else None,
            proxy=ctx.config.get("proxy"),
        )

        self._update_db(task_id, NodeStatus.RUNNING)
        await self._publish(task_id, "node.started", 10, "开始下载视频...")

        try:
            result = await asyncio.to_thread(
                self.router.download_with_fallback, url, dest_dir, opts
            )
        except Vid2NoteError as e:
            self._update_db(task_id, NodeStatus.FAILED, error={"code": e.code, "message": str(e)})
            return NodeResult.failure(self.name, e)
        except Exception as e:  # noqa: BLE001 - 下载器底层异常兜底
            self._update_db(
                task_id, NodeStatus.FAILED, error={"code": "DOWNLOAD_ERROR", "message": str(e)}
            )
            return NodeResult.failure(self.name, "DOWNLOAD_ERROR", str(e))

        video_path = result.video_path
        if video_path is None or not Path(video_path).exists():
            return NodeResult.failure(self.name, "DOWNLOAD_ERROR", "下载完成但未找到视频文件")

        # 落盘产物到标准产物名
        stored_video = self.store.import_file(
            task_id, self.name.value, "video_file", Path(video_path), move=True
        )

        metadata = {
            "video_file": str(stored_video),
            "title": result.metadata.get("title"),
        }
        self._update_db(task_id, NodeStatus.COMPLETED, artifacts=["video_file"], metadata=metadata)
        await self._publish(task_id, "node.completed", 25, "视频下载完成", artifact="video_file")
        return NodeResult.success(
            node=self.name,
            artifacts=[ArtifactRef(node=self.name, name="video_file")],
            metadata=metadata,
        )


class RealExtractAudioNode(PipelineNode, _RealNodeMixin):
    """从视频提取音频：video_file → audio_file（16kHz 单声道 wav）。"""

    name = NodeName.EXTRACT_AUDIO
    requires: list[str] = ["video_file"]
    produces: list[str] = ["audio_file"]

    def __init__(self, extractor=None, store: ArtifactStore | None = None, repository=None):
        self.extractor = extractor or AudioExtractor()
        if store is None:
            raise TypeError("store is required")
        self.store = store
        self.repository = repository

    async def run(self, ctx: TaskContext) -> NodeResult:
        task_id = ctx.task_id.value
        task_dir = self.store.ensure_task_dir(task_id)
        video_path = self.store.artifact_path(task_id, NodeName.DOWNLOAD.value, "video_file")

        self._update_db(task_id, NodeStatus.RUNNING)
        await self._publish(task_id, "node.started", 30, "提取音频中...")

        try:
            audio_path = await asyncio.to_thread(
                self.extractor.extract, video_path, task_dir / "artifacts"
            )
        except Vid2NoteError as e:
            self._update_db(task_id, NodeStatus.FAILED, error={"code": e.code, "message": str(e)})
            return NodeResult.failure(self.name, e)
        except Exception as e:  # noqa: BLE001
            self._update_db(
                task_id,
                NodeStatus.FAILED,
                error={"code": "AUDIO_EXTRACT_FAILED", "message": str(e)},
            )
            return NodeResult.failure(self.name, "AUDIO_EXTRACT_FAILED", str(e))
        stored_audio = self.store.import_file(
            task_id, self.name.value, "audio_file", Path(audio_path), move=True
        )
        metadata = {"audio_file": str(stored_audio)}
        self._update_db(task_id, NodeStatus.COMPLETED, artifacts=["audio_file"], metadata=metadata)
        await self._publish(task_id, "node.completed", 45, "音频提取完成", artifact="audio_file")
        return NodeResult.success(
            node=self.name,
            artifacts=[ArtifactRef(node=self.name, name="audio_file")],
            metadata=metadata,
        )


class RealTranscribeNode(PipelineNode, _RealNodeMixin):
    """语音识别：audio_file → srt_file。"""

    name = NodeName.TRANSCRIBE
    requires: list[str] = ["audio_file"]
    produces: list[str] = ["srt_file"]

    def __init__(self, asr=None, store: ArtifactStore | None = None, repository=None):
        # asr: 实现了 transcribe(audio_path, opts) -> ASRResult 的对象
        self.asr = asr
        if store is None:
            raise TypeError("store is required")
        self.store = store
        self.repository = repository

    async def run(self, ctx: TaskContext) -> NodeResult:
        task_id = ctx.task_id.value
        audio_path = self.store.artifact_path(task_id, NodeName.EXTRACT_AUDIO.value, "audio_file")

        self._update_db(task_id, NodeStatus.RUNNING)
        await self._publish(task_id, "node.started", 50, "语音识别中...")

        asr = self.asr or _default_asr(ctx.config)
        opts = {"language": ctx.config.get("language", "zh")}
        try:
            result = await _maybe_await(asr.transcribe(audio_path, opts))
        except Vid2NoteError as e:
            self._update_db(task_id, NodeStatus.FAILED, error={"code": e.code, "message": str(e)})
            return NodeResult.failure(self.name, e)
        except Exception as e:  # noqa: BLE001
            self._update_db(
                task_id, NodeStatus.FAILED, error={"code": "ASR_ERROR", "message": str(e)}
            )
            return NodeResult.failure(self.name, "ASR_ERROR", str(e))
        srt_text = _asr_result_to_srt(result)
        self.store.write_artifact(task_id, self.name.value, "srt_file", srt_text.encode("utf-8"))
        metadata = {"srt_file": "srt_file", "language": getattr(result, "language", "zh")}
        self._update_db(task_id, NodeStatus.COMPLETED, artifacts=["srt_file"], metadata=metadata)
        await self._publish(task_id, "node.completed", 70, "语音识别完成", artifact="srt_file")
        return NodeResult.success(
            node=self.name,
            artifacts=[ArtifactRef(node=self.name, name="srt_file")],
            metadata=metadata,
        )


class RealOrganizeNode(PipelineNode, _RealNodeMixin):
    """LLM 整理笔记：srt_file → markdown_file。"""

    name = NodeName.ORGANIZE
    requires: list[str] = ["srt_file"]
    produces: list[str] = ["markdown_file"]

    def __init__(self, llm=None, store: ArtifactStore | None = None, repository=None):
        self.llm = llm
        if store is None:
            raise TypeError("store is required")
        self.store = store
        self.repository = repository

    async def run(self, ctx: TaskContext) -> NodeResult:
        task_id = ctx.task_id.value
        srt_bytes = self.store.read_artifact(task_id, NodeName.TRANSCRIBE.value, "srt_file")
        subtitle = srt_bytes.decode("utf-8")

        self._update_db(task_id, NodeStatus.RUNNING)
        await self._publish(task_id, "node.started", 75, "LLM 整理笔记中...")

        llm = self.llm or _default_llm(ctx.config)
        try:
            # restructure_content 是同步阻塞调用，放到线程池
            markdown = await asyncio.to_thread(
                llm.restructure_content, subtitle, ctx.config.get("context", ""), 0.3
            )
        except Vid2NoteError as e:
            self._update_db(task_id, NodeStatus.FAILED, error={"code": e.code, "message": str(e)})
            return NodeResult.failure(self.name, e)
        except Exception as e:  # noqa: BLE001
            self._update_db(
                task_id, NodeStatus.FAILED, error={"code": "LLM_ERROR", "message": str(e)}
            )
            return NodeResult.failure(self.name, "LLM_ERROR", str(e))

        self.store.write_artifact(
            task_id, self.name.value, "markdown_file", markdown.encode("utf-8")
        )
        metadata = {"markdown_file": "markdown_file"}
        self._update_db(
            task_id, NodeStatus.COMPLETED, artifacts=["markdown_file"], metadata=metadata
        )
        await self._publish(task_id, "node.completed", 95, "笔记整理完成", artifact="markdown_file")
        return NodeResult.success(
            node=self.name,
            artifacts=[ArtifactRef(node=self.name, name="markdown_file")],
            metadata=metadata,
        )


class RealRegisterSourceNode(PipelineNode, _RealNodeMixin):
    """Register immutable transcript evidence and a regenerable source note in the Vault."""

    name = NodeName.REGISTER_SOURCE
    requires: list[str] = ["srt_file", "markdown_file"]
    produces: list[str] = ["source_record"]

    def __init__(
        self,
        registrar: SourceRegistrar,
        store: ArtifactStore,
        repository=None,
    ):
        self.registrar = registrar
        self.store = store
        self.repository = repository

    async def run(self, ctx: TaskContext) -> NodeResult:
        task_id = ctx.task_id.value
        task = self.repository.get_by_id(task_id) if self.repository is not None else None
        if task is None:
            return NodeResult.failure(self.name, "SOURCE_TASK_NOT_FOUND", "找不到待注册任务")

        self._update_db(task_id, NodeStatus.RUNNING)
        await self._publish(task_id, "node.started", 96, "注册来源证据...")
        original_path = self.store.artifact_path(task_id, NodeName.DOWNLOAD.value, "video_file")
        imported_at = task.created_at or datetime.now(UTC)
        if imported_at.tzinfo is None:
            imported_at = imported_at.replace(tzinfo=UTC)
        try:
            record = await asyncio.to_thread(
                self.registrar.register,
                SourceRegistration(
                    task_id=task_id,
                    canonical_url=task.video_url,
                    title=task.video_url or task.srt_file or task_id,
                    imported_at=imported_at,
                    srt_path=self.store.artifact_path(
                        task_id, NodeName.TRANSCRIBE.value, "srt_file"
                    ),
                    note_path=self.store.artifact_path(
                        task_id, NodeName.ORGANIZE.value, "markdown_file"
                    ),
                    original_path=original_path if original_path.is_file() else None,
                ),
            )
        except Vid2NoteError as exc:
            self._update_db(
                task_id, NodeStatus.FAILED, error={"code": exc.code, "message": str(exc)}
            )
            return NodeResult.failure(self.name, exc)
        except Exception as exc:  # noqa: BLE001 - convert registration failures to node failure
            self._update_db(
                task_id,
                NodeStatus.FAILED,
                error={"code": "SOURCE_REGISTRATION_FAILED", "message": str(exc)},
            )
            return NodeResult.failure(self.name, "SOURCE_REGISTRATION_FAILED", str(exc))

        payload = json.dumps(record.model_dump(mode="json"), ensure_ascii=False).encode()
        self.store.write_artifact(task_id, self.name.value, "source_record", payload)
        metadata = {"source_id": record.source_id}
        self._update_db(
            task_id, NodeStatus.COMPLETED, artifacts=["source_record"], metadata=metadata
        )
        await self._publish(
            task_id,
            "node.completed",
            97,
            "来源证据已注册",
            artifact="source_record",
        )
        return NodeResult.success(
            node=self.name,
            artifacts=[ArtifactRef(node=self.name, name="source_record")],
            metadata=metadata,
        )


class RealProposeWikiChangesNode(PipelineNode, _RealNodeMixin):
    """Compile a registered source into a pending ChangeSet without editing the Wiki."""

    name = NodeName.PROPOSE_WIKI_CHANGES
    requires: list[str] = ["source_record"]
    produces: list[str] = ["changeset_id"]

    def __init__(
        self,
        *,
        store: ArtifactStore,
        vault: VaultRepository,
        changesets: ChangeSetStore,
        applier: ChangeSetApplier | None = None,
        autonomy_mode_provider=None,
        llm=None,
        repository=None,
    ):
        self.store = store
        self.vault = vault
        self.changesets = changesets
        self.applier = applier
        self.autonomy_mode_provider = autonomy_mode_provider
        self.llm = llm
        self.repository = repository

    async def run(self, ctx: TaskContext) -> NodeResult:
        from vid2note_core.source.models import SourceRecord

        task_id = ctx.task_id.value
        self._update_db(task_id, NodeStatus.RUNNING)
        await self._publish(task_id, "node.started", 97, "分析 Wiki 变更提案...")
        try:
            source = SourceRecord.model_validate_json(
                self.store.read_artifact(
                    task_id,
                    NodeName.REGISTER_SOURCE.value,
                    "source_record",
                )
            )
            note_paths = sorted(self.vault.layout.sources.glob(f"{source.source_id}--*.md"))
            if len(note_paths) != 1:
                raise FileNotFoundError(f"source note for {source.source_id}")
            source_note = self.vault.read_page(
                note_paths[0].relative_to(self.vault.root).as_posix()
            )
            context = WikiRetriever(self.vault).find_context(source.title)
            related_pages = [
                self.vault.read_page(page.path)
                for page in context.pages
                if page.knowledge_layer == "wiki"
            ]
            compiler = WikiCompiler(self.llm or _default_llm(ctx.config))
            result = await asyncio.to_thread(
                compiler.propose,
                CompileInput(
                    source=source,
                    source_note=source_note,
                    schema_text=context.schema_text,
                    index_text=context.index_text,
                    related_pages=related_pages,
                ),
            )
            changeset_id = result.changeset.id if result.changeset is not None else None
            if result.changeset is not None:
                existing = self.changesets.get(result.changeset.id)
                if existing is None:
                    self.changesets.save_pending(result.changeset)
                elif existing != result.changeset:
                    raise FileExistsError(result.changeset.id)
                mode = (
                    self.autonomy_mode_provider()
                    if self.autonomy_mode_provider is not None
                    else AutonomyMode.APPROVAL
                )
                stored = self.changesets.get(result.changeset.id)
                if (
                    AutonomyPolicy(mode).decide(result.classification) == "auto_apply"
                    and self.applier is not None
                    and stored is not None
                    and stored.status == "pending"
                ):
                    self.applier.apply(result.changeset)
            self.store.write_artifact(
                task_id,
                self.name.value,
                "changeset_id",
                (changeset_id or "").encode(),
            )
        except Vid2NoteError as exc:
            self._update_db(
                task_id, NodeStatus.FAILED, error={"code": exc.code, "message": str(exc)}
            )
            return NodeResult.failure(self.name, exc)
        except Exception as exc:  # noqa: BLE001 - normalize proposal failures
            self._update_db(
                task_id,
                NodeStatus.FAILED,
                error={"code": "WIKI_PROPOSAL_FAILED", "message": str(exc)},
            )
            return NodeResult.failure(self.name, "WIKI_PROPOSAL_FAILED", str(exc))

        metadata = {
            "classification": result.classification,
            "changeset_id": changeset_id,
        }
        self._update_db(
            task_id, NodeStatus.COMPLETED, artifacts=["changeset_id"], metadata=metadata
        )
        await self._publish(
            task_id,
            "node.completed",
            98,
            "Wiki 变更提案已生成" if changeset_id else "来源未产生新的 Wiki 变更",
            artifact="changeset_id",
        )
        return NodeResult.success(
            node=self.name,
            artifacts=[ArtifactRef(node=self.name, name="changeset_id")],
            metadata=metadata,
        )


class RealMindmapNode(PipelineNode, _RealNodeMixin):
    """生成思维导图：markdown_file → mindmap_file（Mermaid）。

    用 prompts/mindmap.txt 把整理好的 Markdown 笔记转成 Mermaid mindmap 语法，
    落盘到 ArtifactStore。Mermaid 可被前端直接渲染，后续可再转 xmind/png。
    """

    name = NodeName.MINDMAP
    requires: list[str] = ["markdown_file"]
    produces: list[str] = ["mindmap_file"]

    def __init__(
        self,
        llm=None,
        store: ArtifactStore | None = None,
        mindmap_format: str = "mermaid",
        repository=None,
    ):
        self.llm = llm
        if store is None:
            raise TypeError("store is required")
        self.store = store
        self.mindmap_format = mindmap_format  # "mermaid" 或 "outline"
        self.repository = repository

    def _build_prompt(self, markdown: str) -> str:
        """根据格式选择 prompt 模板并填充内容。"""
        from vid2note_core.prompts import MINDMAP_GENERATION, MINDMAP_OUTLINE

        template = MINDMAP_OUTLINE if self.mindmap_format == "outline" else MINDMAP_GENERATION
        # mindmap.txt 用 {markdown_content}，mindmap_outline.txt 用 {content}
        if "{markdown_content}" in template:
            return template.replace("{markdown_content}", markdown)
        return template.replace("{content}", markdown)

    async def run(self, ctx: TaskContext) -> NodeResult:
        task_id = ctx.task_id.value
        md_bytes = self.store.read_artifact(task_id, NodeName.ORGANIZE.value, "markdown_file")
        markdown = md_bytes.decode("utf-8")

        self._update_db(task_id, NodeStatus.RUNNING)
        await self._publish(task_id, "node.started", 98, "生成思维导图...")

        llm = self.llm or _default_llm(ctx.config)
        prompt = self._build_prompt(markdown)
        messages = [
            {"role": "system", "content": "你是思维导图结构分析专家，只输出结构化内容，不要解释。"},
            {"role": "user", "content": prompt},
        ]

        try:
            mindmap = await asyncio.to_thread(llm.chat, messages, temperature=0.3, max_tokens=3000)
        except Vid2NoteError as e:
            self._update_db(task_id, NodeStatus.FAILED, error={"code": e.code, "message": str(e)})
            return NodeResult.failure(self.name, e)
        except Exception as e:  # noqa: BLE001
            self._update_db(
                task_id, NodeStatus.FAILED, error={"code": "LLM_ERROR", "message": str(e)}
            )
            return NodeResult.failure(self.name, "LLM_ERROR", str(e))

        mindmap = _clean_mindmap_output(mindmap, self.mindmap_format)
        self.store.write_artifact(task_id, self.name.value, "mindmap_file", mindmap.encode("utf-8"))
        metadata = {"mindmap_file": "mindmap_file", "format": self.mindmap_format}
        self._update_db(
            task_id, NodeStatus.COMPLETED, artifacts=["mindmap_file"], metadata=metadata
        )
        await self._publish(
            task_id, "node.completed", 99, "思维导图生成完成", artifact="mindmap_file"
        )
        return NodeResult.success(
            node=self.name,
            artifacts=[ArtifactRef(node=self.name, name="mindmap_file")],
            metadata=metadata,
        )


class RealCleanupNode(PipelineNode, _RealNodeMixin):
    """清理临时文件：按 RetentionConfig 删除 video/audio（默认删），保留 srt。

    清理不影响主链路完成状态（设计稿：cleanup 节点失败不影响 completed）。
    产物是一份删除清单（deletion manifest），落盘到 ArtifactStore 便于审计。
    """

    name = NodeName.CLEANUP
    requires: list[str] = ["markdown_file"]
    produces: list[str] = ["cleanup_manifest"]

    def __init__(self, store: ArtifactStore | None = None, repository=None):
        if store is None:
            raise TypeError("store is required")
        self.store = store
        self.repository = repository

    async def run(self, ctx: TaskContext) -> NodeResult:
        task_id = ctx.task_id.value
        # 从 ctx.config 读保留策略（与 RetentionConfig 字段对齐）
        keep_video = ctx.config.get("keep_video", False)
        keep_audio = ctx.config.get("keep_audio", False)
        # keep_srt 默认 True（与 RetentionConfig 一致），srt/markdown/mindmap 始终保留

        self._update_db(task_id, NodeStatus.RUNNING)
        await self._publish(task_id, "node.started", 99, "清理临时文件...")

        deleted: list[str] = []
        kept: list[str] = []

        # 按保留策略删除 video / audio 产物
        targets = []
        if not keep_video:
            targets.append((NodeName.DOWNLOAD.value, "video_file", "video"))
        else:
            kept.append("video")
        if not keep_audio:
            targets.append((NodeName.EXTRACT_AUDIO.value, "audio_file", "audio"))
        else:
            kept.append("audio")

        for node_name, artifact_name, label in targets:
            try:
                if self.store.exists(task_id, node_name, artifact_name):
                    self.store.delete_artifact(task_id, node_name, artifact_name)
                    deleted.append(artifact_name)
            except Exception:  # noqa: BLE001 - 单个产物删除失败不阻断清理
                kept.append(label)

        # 始终保留：srt、markdown、mindmap
        kept.extend(["srt", "markdown", "mindmap"])

        # 落盘删除清单
        import json

        manifest = {
            "deleted": deleted,
            "kept": kept,
            "keep_video": keep_video,
            "keep_audio": keep_audio,
        }
        self.store.write_artifact(
            task_id,
            self.name.value,
            "cleanup_manifest",
            json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
        )

        metadata = {"cleanup_manifest": "cleanup_manifest", "deleted": deleted, "kept": kept}
        self._update_db(
            task_id,
            NodeStatus.COMPLETED,
            artifacts=["cleanup_manifest"],
            metadata=metadata,
        )
        await self._publish(task_id, "node.completed", 100, "清理完成")
        return NodeResult.success(
            node=self.name,
            artifacts=[ArtifactRef(node=self.name, name="cleanup_manifest")],
            metadata=metadata,
        )


# ── 辅助函数 ─────────────────────────────────────────────


def _default_asr(config: dict):
    """根据 config 创建 ASR。provider 错误或初始化失败时显式抛 ASRError（不再静默回退 mock）。"""
    from vid2note_core.asr.factory import ASRFactory

    provider = config.get("asr_provider", "funasr")
    try:
        asr_config = {}
        if model_manager := config.get("model_manager"):
            asr_config["model_manager"] = model_manager
        return ASRFactory.create(provider, asr_config)
    except ValueError as e:
        raise ASRError(
            f"不支持的 ASR 提供商: {provider}（{e}）",
            code="ASR_PROVIDER_INVALID",
            retryable=False,
            user_message=f"ASR 提供商 {provider} 不可用，请到设置页检查",
            step="transcribe",
        ) from e
    except Exception as e:
        raise ASRError(
            f"ASR 初始化失败: {e}",
            code="ASR_INIT_FAILED",
            retryable=True,
            user_message=f"语音识别初始化失败：{e}",
            step="transcribe",
        ) from e


def _default_llm(config: dict):
    """根据 config 创建 LLM。缺少 API Key 或初始化失败时显式抛 LLMError（不再回退 MockLLM）。"""
    from vid2note_core.llm.factory import LLMFactory

    provider = config.get("llm_provider", "qwen")
    api_key = config.get("api_key", "")
    if not api_key:
        raise LLMError(
            f"LLM provider {provider} 缺少 API Key",
            code="LLM_API_KEY_MISSING",
            retryable=False,
            user_message=f"未配置 {provider} 的 API Key，请到设置页填写",
            step="organize",
        )
    try:
        llm_config = {"api_key": api_key, "model": config.get("llm_model")}
        if provider == "baidu":
            llm_config["secret_key"] = config.get("secret_key", "")
        return LLMFactory.create(provider, llm_config)
    except Exception as e:
        raise LLMError(
            f"LLM 初始化失败: {e}",
            code="LLM_INIT_FAILED",
            retryable=False,
            user_message=f"AI 服务初始化失败：{e}",
            step="organize",
        ) from e


def _format_timestamp(ms: int) -> str:
    """毫秒 → SRT 时间码 HH:MM:SS,mmm"""
    if ms < 0:
        ms = 0
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    seconds, ms = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"


def _asr_result_to_srt(result) -> str:
    """ASRResult → SRT 文本。"""
    segments = getattr(result, "segments", None) or []
    if not segments:
        # 无分段时退化为单段纯文本
        text = getattr(result, "text_full", "") or str(result)
        return f"1\n00:00:00,000 --> 00:00:01,000\n{text}\n"
    lines = []
    for i, seg in enumerate(segments, 1):
        start = _format_timestamp(getattr(seg, "start_ms", 0))
        end = _format_timestamp(getattr(seg, "end_ms", 0))
        text = getattr(seg, "text", "")
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)


async def _maybe_await(value):
    """transcribe 可能是同步或异步：统一为 await 结果。"""
    if asyncio.iscoroutine(value):
        return await value
    return value


def _clean_mindmap_output(text: str, mindmap_format: str) -> str:
    """清理 LLM 输出：去掉可能存在的代码块包裹与多余空白。

    prompt 虽要求"不要包裹代码块"，但模型有时仍会包裹，这里兜底剥离。
    mermaid 格式会保留首部 mindmap 关键字；outline 格式保持纯缩进文本。
    """
    if not text:
        return ""
    text = text.strip()
    # 剥离 ```mermaid / ``` 包裹
    if text.startswith("```"):
        lines = text.splitlines()
        # 去掉首行（``` 或 ```mermaid）
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        # 去掉末行 ```（若有）
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text
