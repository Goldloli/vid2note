"""
runtime.runner —— v1 任务运行栈的执行入口(契约 §5 / §6 / 设计 D8)
=================================================================

:func:`run_task` 把一个已入库的任务编排为六步 DAG,由 ``pipeline.dag.DagRunner`` 推进
状态机,各节点执行器接入真实模块:

- ``download`` → :func:`media_ingest.download_video`(在线来源;本地来源由 DAG 跳过)
- ``extract_audio`` → :func:`media_ingest.extract_audio`
- ``asr`` → :func:`speech_to_text.transcribe`
- ``note`` → 内核 :class:`SimpleProcessor.process`(无 PDF 走 generate_directly 分支 /
  有 PDF 走 generate_with_pdf_reference 分支)+ 清洗 ``` 包裹;
  ``extract_images=True`` 时调 :func:`screenshot.embed_screenshots`
- ``mindmap`` → 内核 :func:`SimpleProcessor.generate_mindmap`(按 ``mindmap_formats`` 多格式)
- ``cleanup`` → :func:`retention.cleanup_task_temp`

每个节点状态变化「先落库(``RepoStateAdapter``)再推 SSE(``SSEBusAdapter``)」由 DAG
框架统一保证(契约 §0 第 5 条);产物以相对 ``DATA_ROOT`` 的 POSIX 路径回写任务;
支持取消(:class:`CancelToken`,契约 §0.6)。

内核边界(契约 §0.2):``SimpleProcessor`` / ``LLMFactory`` / ``logger`` / ``TaskLogger``
均经 ``from src.core.kernel import`` 取。
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from src.core.kernel import (
    LLMFactory,
    SimpleProcessor,
    TaskLogger,
    TaskRepository,
    logger,
)
from src.pipeline import (
    CancelToken,
    NodeName,
    NodeStatus,
    NODE_ORDER,
    PipelineCancelled,
    TaskState,
    TaskStatus as PipelineTaskStatus,
    run_task_dag,
    skip_nodes_for,
)
from src.pipeline.dag import NodeState

from .adapters import RepoStateAdapter, SSEBusAdapter, get_cancel_registry
from .settings import (
    get_bilibili_cookies,
    get_credentials,
    get_external_asr_api_key,
    get_settings_snapshot,
)


# --------------------------------------------------------------------------- #
# 路径与工具
# --------------------------------------------------------------------------- #
def _default_data_root() -> Path:
    """DATA_ROOT 默认 ``backend/data``(可由环境变量 ``DATA_ROOT`` 覆盖,契约 §2.3)。"""
    env = os.environ.get("DATA_ROOT")
    if env:
        return Path(env)
    # backend/src/runtime/runner.py → parents[2] = backend/
    return Path(__file__).resolve().parents[2] / "data"


def _strip_code_fence(text: str) -> str:
    """清洗 LLM 输出首尾的 ``` / ```markdown 包裹(契约 §5.6 / §6.4 第 5 条)。

    仅剥首尾成对围栏;正文中的代码块保留。``\`\`\`markdown\\n...\n\`\`\``` → 内部正文。
    """
    if not text:
        return ""
    s = text.strip()
    if not s.startswith("```"):
        return s
    lines = s.splitlines()
    # 去首行围栏(``` 或 ```markdown 等)
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    # 去末行围栏(仅当成行 ```)
    while lines and lines[-1].strip() == "":
        lines.pop()
    if lines and lines[-1].strip().startswith("```"):
        lines.pop()
    return "\n".join(lines).strip()


def _source_type_enum(value: Any) -> Any:
    """把任务 ``source_type`` 字符串归一为 ``media_ingest.SourceType`` 枚举。"""
    from src.media_ingest import SourceType

    if isinstance(value, SourceType):
        return value
    s = str(value or "").strip().lower()
    for st in SourceType:
        if st.value == s:
            return st
    return SourceType.DIRECT


def _note_stage_progress(
    phase: str,
    completed: int,
    total: int,
) -> tuple[int, str]:
    """把超详细内部阶段映射成单调且面向用户的节点进度。"""
    if phase == "understand":
        percent = 30 + round((completed / max(1, total)) * 25)
        return percent, f"正在理解字幕第 {completed}/{total} 段"
    if phase == "blueprint":
        return 62, "正在构建课程知识结构"
    if phase == "draft":
        percent = 62 + round((completed / max(1, total)) * 12)
        return percent, f"正在撰写第 {completed}/{total} 章"
    percent = 74 + round((completed / max(1, total)) * 10)
    return percent, f"正在审校第 {completed}/{total} 章"


# --------------------------------------------------------------------------- #
# LLM 用量聚合(openspec change add-llm-usage-observability)
# --------------------------------------------------------------------------- #
# 用量桶数值字段(与 llm.openai_compatible.normalize_usage 产出一致,外加 calls)
_USAGE_NUMERIC_FIELDS: tuple[str, ...] = (
    "prompt_tokens",
    "completion_tokens",
    "cache_hit_tokens",
    "cache_miss_tokens",
)


def classify_llm_operation(operation_name: str) -> str:
    """把 LLM 操作名归类为用量阶段键。

    understand(超详细字幕理解/语义证据)→ blueprint(蓝图及修复)→
    draft(章节初稿)→ review(章节审校/格式修复/术语保真)→
    mindmap(思维导图)→ other(PDF 结构分析、普通笔记生成等)。
    判断顺序先精确后宽泛,命中即返回。
    """
    name = str(operation_name or "")
    if "超详细字幕理解" in name or "语义证据" in name:
        return "understand"
    if "蓝图" in name:
        return "blueprint"
    if "章节初稿" in name:
        return "draft"
    if "章节审校" in name or "章节格式修复" in name or "术语保真" in name:
        return "review"
    if "思维导图" in name:
        return "mindmap"
    return "other"


class LlmUsageAggregator:
    """任务级 LLM 用量聚合器:total / by_stage / by_operation 两级累计。

    当前全部 LLM 调用串行(``_call_llm`` 无并发),实例由 note / mindmap 两个
    节点执行器共享,无需加锁;by_operation 每项额外带 ``stage`` 键。
    """

    def __init__(self) -> None:
        self._total = self._new_bucket()
        self._by_stage: Dict[str, Dict[str, int]] = {}
        self._by_operation: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _new_bucket() -> Dict[str, int]:
        bucket = {field: 0 for field in _USAGE_NUMERIC_FIELDS}
        bucket["calls"] = 0
        return bucket

    def record(self, operation_name: str, usage: Dict[str, Any]) -> None:
        """累计一次调用(``usage`` 为 normalize_usage 产出的归一化 dict)。"""
        stage = classify_llm_operation(operation_name)
        operation_bucket = self._by_operation.setdefault(
            str(operation_name), {"stage": stage, **self._new_bucket()}
        )
        for bucket in (
            self._total,
            self._by_stage.setdefault(stage, self._new_bucket()),
            operation_bucket,
        ):
            bucket["calls"] += 1
            for field in _USAGE_NUMERIC_FIELDS:
                bucket[field] += int(usage.get(field, 0) or 0)

    def to_dict(self) -> Dict[str, Any]:
        """产出落库结构 ``{"total": {...}, "by_stage": {...}, "by_operation": {...}}``。"""
        return {
            "total": dict(self._total),
            "by_stage": {key: dict(value) for key, value in self._by_stage.items()},
            "by_operation": {
                key: dict(value) for key, value in self._by_operation.items()
            },
        }


# --------------------------------------------------------------------------- #
# LLM 构造
# --------------------------------------------------------------------------- #
def _build_llm(snapshot: Dict[str, str], task: Any) -> Any:
    """据快照 + 任务选项构造内核 LLM 实例(契约 §0.2 经 LLMFactory)。

    优先级:任务自带 ``llm_provider`` / ``llm_model`` > 快照默认。凭证取自快照的
    ``llm.credentials``(按 provider 聚合或扁平形态,见 :func:`settings.get_credentials`)。
    缺凭证/非法配置由 :func:`LLMFactory.create` 抛错,上游节点据此转 failed。
    """
    provider = (getattr(task, "llm_provider", None) or snapshot.get("llm.provider") or "deepseek")
    provider = str(provider).strip().lower() or "deepseek"
    model = getattr(task, "llm_model", None) or snapshot.get("llm.model") or "deepseek-v4-flash"
    model = str(model).strip() or "deepseek-v4-flash"

    creds = get_credentials(snapshot, provider)
    config: Dict[str, Any] = dict(creds)
    # 任务指定的模型覆盖凭证中的模型
    config["model"] = model
    # LLMFactory.create 单独收 provider,配置里不得重复
    config.pop("provider", None)
    return LLMFactory.create(provider, config)


# --------------------------------------------------------------------------- #
# NodeContext 透传代理:补 work_temp(media_ingest.download_video 需要)
# --------------------------------------------------------------------------- #
class _NodeContextExt:
    """给 DAG ``NodeContext`` 透传补 ``work_temp``(契约 §0.7 临时隔离)。

    ``download_video`` 直接读 ``ctx.work_temp``(分片写 ``data/temp/<tid>/``),
    而 ``NodeContext`` 不带该属性;本代理转发其余属性方法、注入 work_temp。
    """

    def __init__(self, ctx: Any, work_temp: Path) -> None:
        self._ctx = ctx
        self.work_temp = work_temp

    def __getattr__(self, name: str) -> Any:
        return getattr(self._ctx, name)


# --------------------------------------------------------------------------- #
# 初始 TaskState 构造(fresh 含来源/mindmap 跳过;非 fresh 加载既有状态)
# --------------------------------------------------------------------------- #
def _build_initial_state(task: Any) -> TaskState:
    """构造 DAG 初始 :class:`TaskState`。

    - **fresh 任务**(status=pending 且无节点启动):用 :meth:`TaskState.fresh` 构造,
      按来源跳过 download/extract_audio;``mindmap_formats == []`` 时跳过 mindmap。
    - **既有任务**(重跑 / 恢复):从 ``task.node_statuses`` 与顶层产物指针加载,
      保留各节点既有状态供 ``DagRunner`` 重跑/恢复判定。

    注:v1 ``Task`` 创建时 ``node_statuses`` 全 pending(未应用来源跳过),故 fresh 任务
    必须走 :meth:`TaskState.fresh` 才能正确标记 local_* 的 download/extract_audio 跳过。
    """
    ns = task.node_statuses or {}
    any_started = any(
        isinstance(ns.get(n.value), dict) and ns[n.value].get("status") != NodeStatus.PENDING.value
        for n in NODE_ORDER
    )
    task_status = getattr(task, "status", None)
    task_status_val = task_status.value if hasattr(task_status, "value") else str(task_status)
    is_fresh = task_status_val == PipelineTaskStatus.PENDING.value and not any_started

    if is_fresh:
        skip = skip_nodes_for(task.source_type)
        if not (getattr(task, "mindmap_formats", None)):
            skip.add(NodeName.MINDMAP)
        return TaskState.fresh(task.id, task.source_type, skip=skip)

    # 既有状态加载
    state = TaskState(task_id=task.id, source_type=str(task.source_type))
    try:
        state.status = PipelineTaskStatus(task_status_val)
    except ValueError:
        state.status = PipelineTaskStatus.PENDING
    state.error = getattr(task, "error", None)
    for n in NODE_ORDER:
        state.nodes[n] = NodeState.from_dict(ns.get(n.value) or {})
    for kind, fld in (
        ("video", "video_path"),
        ("audio", "audio_path"),
        ("srt", "srt_path"),
        ("note", "note_path"),
    ):
        v = getattr(task, fld, None)
        if v:
            state.artifacts[kind] = str(v)
    state.mindmap_paths = list(getattr(task, "mindmap_paths", []) or [])
    state.screenshot_paths = list(getattr(task, "screenshot_paths", []) or [])
    return state


# --------------------------------------------------------------------------- #
# 节点执行器构造
# --------------------------------------------------------------------------- #
def _make_executors(
    task: Any,
    snapshot: Dict[str, str],
    data_root: Path,
    repo: Any = None,
) -> Dict[NodeName, Callable[[Any], None]]:
    """构造六节点执行器 ``{NodeName → Callable[[NodeContext], None]}``。

    执行器内经 ``ctx`` 登记/推进产物与进度,抛 :class:`PipelineCancelled` 触发取消、
    抛其它异常触发节点失败(由 DAG 捕获处理)。
    """
    task_id = task.id

    # note / mindmap 两节点共享的任务级 LLM 用量聚合器(全部调用串行)
    llm_usage_aggregator = LlmUsageAggregator()

    def _flush_llm_usage() -> None:
        """把当前聚合快照落库到 tasks.llm_usage;失败只记日志不阻断节点。"""
        if repo is None:
            return
        try:
            repo.update(task_id, llm_usage=llm_usage_aggregator.to_dict())
        except Exception:  # noqa: BLE001 - 用量落库失败不阻断任务
            logger.debug("LLM 用量落库失败 task=%s", task_id, exc_info=True)

    # ---------------- download ----------------
    def _download(ctx: Any) -> None:
        from src.media_ingest import IngestCancelled, download_video

        source_url = getattr(task, "source_url", None) or ""
        source_type = _source_type_enum(task.source_type)
        cookies = (
            get_bilibili_cookies(snapshot)
            if source_type.value == "bilibili"
            else None
        )
        ctx_ext = _NodeContextExt(ctx, data_root / "temp" / task_id)
        ctx_ext.work_temp.mkdir(parents=True, exist_ok=True)
        try:
            download_video(ctx_ext, source_url, source_type, cookies)
        except IngestCancelled as exc:
            raise PipelineCancelled() from exc
        # 视频标题存 task.title(列表统一命名用;openspec change frontend-fix-naming-mindmap)
        _vt = getattr(ctx_ext, "_video_title", None)
        if _vt and repo is not None:
            try:
                repo.update(task_id, title=_vt)
                task.title = _vt
            except Exception:  # noqa: BLE001
                logger.debug("更新视频标题失败 task=%s", task_id, exc_info=True)

    # ---------------- extract_audio ----------------
    def _extract_audio(ctx: Any) -> None:
        from src.media_ingest import ExtractError, IngestCancelled, extract_audio

        video_rel = ctx._state.artifact("video") or getattr(task, "video_path", None)
        if not video_rel:
            raise ExtractError("音频提取失败:缺少上游视频产物")
        try:
            extract_audio(ctx, video_rel)
        except IngestCancelled as exc:
            raise PipelineCancelled() from exc

    # ---------------- asr ----------------
    def _asr(ctx: Any) -> None:
        from src.speech_to_text import AsrConfig, CancelledError as AsrCancelled, transcribe

        audio_rel = ctx._state.artifact("audio") or getattr(task, "audio_path", None)
        if not audio_rel:
            from src.speech_to_text import AsrError

            raise AsrError("ASR 转录失败:缺少上游音频产物", reason="invalid_response", engine="runtime")
        srt_out_rel = ctx.rel_of(ctx.product_path("srt", "srt"))
        asr_config = AsrConfig.from_settings(snapshot)
        asr_config.external_api_key = get_external_asr_api_key()
        try:
            transcribe(ctx, audio_rel, srt_out_rel, asr_config)
        except AsrCancelled as exc:
            raise PipelineCancelled() from exc

    # ---------------- note ----------------
    def _note(ctx: Any) -> None:
        srt_rel = ctx._state.artifact("srt") or getattr(task, "srt_path", None)
        if not srt_rel:
            raise RuntimeError("笔记生成失败:缺少上游 SRT 产物")
        srt_abs = data_root / srt_rel
        if not srt_abs.exists():
            raise FileNotFoundError(f"笔记生成失败:SRT 文件不存在({srt_rel})")
        pdf_rel = getattr(task, "pdf_path", None)
        pdf_abs = (data_root / pdf_rel) if pdf_rel else None
        if pdf_abs is not None and not pdf_abs.exists():
            # PDF 缺失不阻断笔记生成:降级为无 PDF 直接生成
            logger.warning("任务 %s 附带 PDF 不存在(%s),降级为无 PDF 直接生成", task_id, pdf_rel)
            pdf_abs = None

        ctx.emit_log("info", "开始生成笔记" + ("(含 PDF 讲义参考)" if pdf_abs else ""))
        ctx.emit_progress(5, "初始化笔记生成")
        llm = _build_llm(snapshot, task)

        def _report_note_stage(
            phase: str,
            completed: int,
            total: int,
        ) -> None:
            percent, message = _note_stage_progress(phase, completed, total)
            ctx.emit_progress(percent, message)

        processor = SimpleProcessor(
            llm,
            config={
                "note_detail_level": getattr(
                    task, "note_detail_level", "balanced"
                ),
                "progress_callback": _report_note_stage,
                "usage_callback": llm_usage_aggregator.record,
            },
            logger=TaskLogger(task_id),
        )

        ctx.emit_progress(30, "调用 LLM 生成笔记")
        # 无 PDF 走 generate_directly 分支;有 PDF 走 generate_with_pdf_reference 分支
        # (SimpleProcessor.process 内部据 pdf_file 是否为空自动分流)
        markdown = processor.process(str(srt_abs), str(pdf_abs) if pdf_abs else None, extract_images=bool(getattr(task, "extract_images", False)))
        markdown = _strip_code_fence(markdown)
        ctx.emit_progress(88, "高质量笔记生成完成，准备落盘")

        # 截图嵌入(extract_images=True 时;契约 §6.3)
        if getattr(task, "extract_images", False):
            markdown = _embed_screenshots(ctx, task, markdown, data_root)

        # 落盘 notes/<tid>/note.md
        note_abs = ctx.product_path("note", "md")
        note_abs.parent.mkdir(parents=True, exist_ok=True)
        note_abs.write_text(markdown, encoding="utf-8")
        note_rel = ctx.rel_of(note_abs)
        ctx.register_product("note", note_rel, note_abs.stat().st_size)
        # 提取笔记首个 H1 作为任务标题(列表统一命名 MM-DD 标题·来源 用;openspec change frontend-unified-list-naming)
        import re
        _m = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
        if _m:
            _h1 = _m.group(1).strip().strip("*`#_>").strip()
            if _h1 and repo is not None:
                try:
                    repo.update(task_id, title=_h1)
                    task.title = _h1
                except Exception:  # noqa: BLE001 - 更新 title 失败不阻断笔记生成
                    logger.debug("提取笔记 H1 更新 title 失败 task=%s", task_id, exc_info=True)
        ctx.emit_log("ok", f"笔记已落盘({len(markdown)} 字符)")
        # 笔记节点成功后落库当前用量快照(mindmap 可选,先写一次保证增量可见)
        _flush_llm_usage()

    # ---------------- mindmap ----------------
    def _mindmap(ctx: Any) -> None:
        formats = list(getattr(task, "mindmap_formats", None) or [])
        if not formats:
            # 空列表:不导出,节点空过(由 fresh state 标 skipped;重跑至此则空过)
            ctx.emit_log("info", "未选择思维导图格式,跳过导图生成")
            return
        note_rel = ctx._state.artifact("note") or getattr(task, "note_path", None)
        if not note_rel:
            raise RuntimeError("思维导图生成失败:缺少上游笔记产物")
        note_abs = data_root / note_rel
        if not note_abs.exists():
            raise FileNotFoundError(f"思维导图生成失败:笔记文件不存在({note_rel})")
        markdown = note_abs.read_text(encoding="utf-8")

        llm = _build_llm(snapshot, task)
        processor = SimpleProcessor(
            llm,
            config={"usage_callback": llm_usage_aggregator.record},
            logger=TaskLogger(task_id),
        )
        ctx.emit_log("info", f"开始生成思维导图,格式:{','.join(formats)}")
        ctx.emit_progress(10, "调用 LLM 生成导图大纲")

        for fmt in formats:
            fmt = str(fmt).strip().lower()
            if fmt not in ("xmind", "png", "md"):
                raise ValueError("v1 仅支持 xmind/png/md")
            if fmt == "md":
                # md 格式:直接落盘笔记副本(内核 generate_mindmap 不产 md,这里补)
                out_abs = ctx.product_path("mindmap", "md")
                out_abs.write_text(markdown, encoding="utf-8")
            else:
                out_abs = ctx.product_path("mindmap", fmt)
                produced = processor.generate_mindmap(markdown, out_abs, format=fmt)
                # generate_mindmap 在 XMind/Playwright 不可用时可能回落 .txt 后缀
                produced_path = Path(produced) if produced else out_abs
                if produced_path != out_abs and produced_path.exists():
                    out_abs = produced_path
            if out_abs.exists():
                rel = ctx.rel_of(out_abs)
                ctx.register_product("mindmap", rel, out_abs.stat().st_size)
            else:
                logger.warning("任务 %s 思维导图格式 %s 未产出文件,跳过登记", task_id, fmt)
        ctx.emit_log("ok", f"思维导图已生成({len(formats)} 种格式)")
        # 思维导图节点成功后再次落库用量快照(含导图大纲调用)
        _flush_llm_usage()

    # ---------------- cleanup ----------------
    def _cleanup(ctx: Any) -> None:
        from src.retention import cleanup_task_temp

        ctx.emit_log("info", "清理任务临时文件")
        cleanup_task_temp(task_id, data_root)

    return {
        NodeName.DOWNLOAD: _download,
        NodeName.EXTRACT_AUDIO: _extract_audio,
        NodeName.ASR: _asr,
        NodeName.NOTE: _note,
        NodeName.MINDMAP: _mindmap,
        NodeName.CLEANUP: _cleanup,
    }


def _embed_screenshots(ctx: Any, task: Any, markdown: str, data_root: Path) -> str:
    """note 节点截图嵌入桥接(契约 §6.3 / screenshot 包 docstring 示例)。

    把 ctx 形态的契约签名桥接到 screenshot.embed_screenshots 纯函数;逐标记 ffmpeg
    截帧到 ``screenshots/<tid>/``,替换为相对笔记目录的 Markdown 图片 src,并登记产物。
    """
    from src.screenshot import embed_screenshots

    video_rel = ctx._state.artifact("video") or getattr(task, "video_path", None)
    video_abs = str(data_root / video_rel) if video_rel else None
    shots_dir = ctx.product_path("screenshot", "png").parent
    note_dir = data_root / "notes" / task.id
    note_dir.mkdir(parents=True, exist_ok=True)
    cleaned, srcs = embed_screenshots(
        markdown_text=markdown,
        video_path=video_abs,
        screenshots_dir=shots_dir,
        image_rel_from=note_dir,
    )
    # 把「相对笔记目录」的 src 换算为「相对 DATA_ROOT」的产物路径并登记
    for src in srcs:
        shot_abs = (note_dir / src).resolve()
        try:
            if shot_abs.exists():
                # 必须先归一化再登记，避免数据库保存 notes/<id>/../../screenshots/...。
                rel = shot_abs.relative_to(data_root.resolve()).as_posix()
                ctx.register_product("screenshot", rel, shot_abs.stat().st_size)
        except (ValueError, OSError):  # 单张截图越界/登记失败不中断笔记
            logger.debug("截图产物登记失败 task=%s src=%s", task.id, src, exc_info=True)
    return cleaned


# --------------------------------------------------------------------------- #
# 公共入口:run_task
# --------------------------------------------------------------------------- #
def run_task(
    task_id: str,
    *,
    from_node: Optional[str] = None,
    repo: Optional[TaskRepository] = None,
    bus: Any = None,
    data_root: Optional[Path] = None,
    settings: Optional[Dict[str, str]] = None,
    loop: Any = None,
    cancel_registry: Any = None,
    task: Any = None,
) -> TaskState:
    """编排并执行一个任务(契约 §5 / §6)。

    Args:
        task_id: 任务 ID。
        from_node: 节点级重跑起始节点(六节点之一);``None`` 为完整执行。
        repo: 任务仓库;``None`` 时新建 :class:`TaskRepository`。
        bus: SSE 总线(同步 publish 接口);``None`` 且 ``loop`` 给定时用 SSEBusAdapter
            桥接异步 :func:`sse.get_bus`,否则不推 SSE(单测可用桩)。
        data_root: 产物根;``None`` 取 :func:`_default_data_root`。
        settings: 设置快照;``None`` 时从仓库读取 + 补默认。
        loop: worker 事件循环(供 SSEBusAdapter 投递事件);``None`` 不推 SSE。
        cancel_registry: CancelToken 注册表;``None`` 用全局单例。
        task: 已加载的任务对象(避免重复读库);``None`` 时从仓库读。

    Returns:
        最终 :class:`TaskState`(已落库 + 回写任务对象)。

    Raises:
        KeyError: 任务不存在。
    """
    repo = repo or TaskRepository()
    data_root = Path(data_root) if data_root else _default_data_root()
    data_root.mkdir(parents=True, exist_ok=True)
    cancel_registry = cancel_registry or get_cancel_registry()

    task_obj = task if task is not None else repo.get_by_id(task_id)
    if task_obj is None:
        raise KeyError(f"任务不存在:{task_id}")

    snapshot = settings if settings is not None else get_settings_snapshot(repo)

    # SSE 适配:bus 为 None 时按 loop 决定是否桥接异步 SSEBus
    bus_adapter = bus
    if bus_adapter is None and loop is not None:
        try:
            from src.sse import get_bus

            bus_adapter = SSEBusAdapter(get_bus(), loop)
        except Exception:  # noqa: BLE001 - SSE 不可用不阻断运行
            logger.debug("SSE 总线初始化失败,本次运行不推事件 task=%s", task_id, exc_info=True)
            bus_adapter = None

    repo_adapter = RepoStateAdapter(repo)
    state = _build_initial_state(task_obj)
    executors = _make_executors(task_obj, snapshot, data_root, repo)

    cancel = CancelToken()
    cancel_registry.register(task_id, cancel)

    try:
        logger.info("开始运行任务 task=%s from_node=%s", task_id, from_node)
        final_state = run_task_dag(
            task_obj,
            download=executors[NodeName.DOWNLOAD],
            extract_audio=executors[NodeName.EXTRACT_AUDIO],
            asr=executors[NodeName.ASR],
            note=executors[NodeName.NOTE],
            mindmap=executors[NodeName.MINDMAP],
            cleanup=executors[NodeName.CLEANUP],
            state=state,
            repo=repo_adapter,
            bus=bus_adapter,
            settings=snapshot,
            data_root=data_root,
            cancel=cancel,
            from_node=from_node,
        )
        # 最终落库兜底(确保 task 字段与 state 同步;run_task_dag 已写回 task 对象)
        RepoStateAdapter(repo).update_task_state(task_id, final_state)
        return final_state
    finally:
        cancel_registry.unregister(task_id)


__all__ = ["run_task", "classify_llm_operation", "LlmUsageAggregator"]
