"""
任务数据模型（v1 重写）

定义 v1 六步 DAG 任务的数据类与枚举,严格依据 CONTRACT §1。
基底旧字段(current_step / message / download_url / *_file / *_original_name /
export_mindmap / error_message 等)已废弃,由 node_statuses / *_path / mindmap_formats /
error 等新字段替代。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------
class TaskStatus(str, Enum):
    """任务总体状态枚举(契约 §1.1 / §1.3)。

    取值与 ``src.pipeline.states.TaskStatus`` 对齐,二者均为 ``str`` 枚举、
    取值一致,可按字符串值互换比较。
    """

    PENDING = "pending"        # 已入队,等待 worker 取起
    RUNNING = "running"        # 运行中(某节点正在执行)
    COMPLETED = "completed"    # 全部非 skipped 节点完成
    FAILED = "failed"          # 某节点失败 / 重启中断
    CANCELLED = "cancelled"    # 用户取消


# 合法状态集合(便于外部校验)
TASK_STATUSES: frozenset[str] = frozenset(s.value for s in TaskStatus)
# 终态:completed / failed / cancelled
TERMINAL_TASK_STATUSES: frozenset[str] = frozenset(
    {TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value}
)


# ---------------------------------------------------------------------------
# 六节点 node_statuses 结构(契约 §1.2)
# ---------------------------------------------------------------------------
# 节点名固定六枚,顺序即 DAG 拓扑序,MUST NOT 改变。
NODE_NAMES: tuple[str, ...] = (
    "download",
    "extract_audio",
    "asr",
    "note",
    "mindmap",
    "cleanup",
)

# 节点状态枚举值(节点级,比任务级多一个 skipped)
NODE_PENDING = "pending"
NODE_RUNNING = "running"
NODE_COMPLETED = "completed"
NODE_FAILED = "failed"
NODE_SKIPPED = "skipped"


def default_node_statuses() -> Dict[str, Dict[str, Any]]:
    """构造六节点初始状态(全部 pending,无产物、无时间戳)。

    用于新任务入库时的默认 ``node_statuses``(契约 §1.2)。
    返回全新 dict,避免可变默认共享。
    """
    return {
        name: {
            "status": NODE_PENDING,
            "progress": 0,
            "started_at": None,
            "finished_at": None,
            "error": None,
            "product": None,
        }
        for name in NODE_NAMES
    }


# ---------------------------------------------------------------------------
# JSON 列(落库前 dumps,读出后 loads;空值存 [] / {},MUST NOT 存 NULL)
# ---------------------------------------------------------------------------
JSON_LIST_FIELDS: tuple[str, ...] = ("mindmap_paths", "screenshot_paths", "mindmap_formats")
JSON_DICT_FIELDS: tuple[str, ...] = ("node_statuses",)
JSON_FIELDS: frozenset[str] = frozenset(JSON_LIST_FIELDS + JSON_DICT_FIELDS)


def _safe_json_loads(value: Any, default: Any) -> Any:
    """安全反序列化 JSON 列:None / 空串 / 解析失败 → 返回默认空结构。"""
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def _parse_datetime(value: Any) -> Optional[datetime]:
    """安全解析 datetime,非法/空值返回 None。"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _coerce_status(value: Any) -> TaskStatus:
    """把任意值归一为 TaskStatus;无法识别时回落 PENDING(避免脏数据抛错)。"""
    if isinstance(value, TaskStatus):
        return value
    try:
        return TaskStatus(str(value))
    except (ValueError, KeyError):
        return TaskStatus.PENDING


# ---------------------------------------------------------------------------
# Task dataclass
# ---------------------------------------------------------------------------
@dataclass
class Task:
    """v1 任务数据类(契约 §1.1)。

    所有产物路径均为相对 ``DATA_ROOT`` 的 POSIX 相对路径,
    由使用方 ``Path(DATA_ROOT) / rel`` 解析为绝对路径(契约 §0.4)。
    """

    # ---- 标识与来源 ----
    id: str
    source_type: str                                  # youtube/bilibili/direct/local_video/local_audio
    source_url: Optional[str] = None                  # 在线来源链接;local_* 为 None
    title: Optional[str] = None                       # 任务标题(视频标题/上传文件名)

    # ---- 总体状态 ----
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0                                 # 0-100,六节点进度加权聚合

    # ---- 产物路径(相对 DATA_ROOT)----
    video_path: Optional[str] = None
    audio_path: Optional[str] = None
    srt_path: Optional[str] = None
    note_path: Optional[str] = None
    pdf_path: Optional[str] = None                    # 用户附带的 PDF 讲义(输入,非产物)
    mindmap_paths: List[str] = field(default_factory=list)
    screenshot_paths: List[str] = field(default_factory=list)

    # ---- 六节点权威视图 ----
    node_statuses: Dict[str, Dict[str, Any]] = field(default_factory=default_node_statuses)

    # ---- 引擎与生成选项 ----
    llm_provider: Optional[str] = None                # qwen/glm/deepseek/...
    llm_model: Optional[str] = None                   # 如 deepseek-v4-flash
    asr_engine: Optional[str] = None                  # bcut/whisper_cpp/external
    pdf_mode: str = "pypdf"                           # 基础 PDF 文本提取
    extract_images: bool = False                      # 截图嵌入开关(默认关)
    output_language: str = "zh"                       # zh / en
    note_detail_level: str = "balanced"               # concise/balanced/detailed/exhaustive
    mindmap_formats: List[str] = field(default_factory=lambda: ["xmind"])

    # ---- 队列 ----
    queue_position: Optional[int] = None              # pending 任务的 FIFO 位次;运行/终态为 None

    # ---- 错误与时间 ----
    error: Optional[str] = None                       # 总体/失败节点中文错误信息
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None            # 进入终态时间

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典(API / JSON 消费)。

        枚举输出字面量值,datetime 输出 ISO 字符串(无值输出 None),
        JSON 字段输出原生 list/dict(便于前端直接消费)。
        """
        return {
            "id": self.id,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "title": self.title,
            "status": self.status.value,
            "progress": self.progress,
            "video_path": self.video_path,
            "audio_path": self.audio_path,
            "srt_path": self.srt_path,
            "note_path": self.note_path,
            "pdf_path": self.pdf_path,
            "mindmap_paths": list(self.mindmap_paths),
            "screenshot_paths": list(self.screenshot_paths),
            "node_statuses": dict(self.node_statuses),
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "asr_engine": self.asr_engine,
            "pdf_mode": self.pdf_mode,
            "extract_images": self.extract_images,
            "output_language": self.output_language,
            "note_detail_level": self.note_detail_level,
            "mindmap_formats": list(self.mindmap_formats),
            "queue_position": self.queue_position,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """从字典构造(API 入参 / 反序列化)。未知键忽略,缺失键取默认值。"""
        node_statuses = data.get("node_statuses") or {}
        if isinstance(node_statuses, str):
            node_statuses = _safe_json_loads(node_statuses, default_node_statuses())
        # 若仅给出部分节点,补齐缺失节点为 pending(保持六节点完整)
        if not isinstance(node_statuses, dict) or not node_statuses:
            node_statuses = default_node_statuses()
        else:
            base = default_node_statuses()
            base.update(node_statuses)
            node_statuses = base

        return cls(
            id=data["id"],
            source_type=data.get("source_type", ""),
            source_url=data.get("source_url"),
            title=data.get("title"),
            status=_coerce_status(data.get("status", TaskStatus.PENDING.value)),
            progress=int(data.get("progress", 0) or 0),
            video_path=data.get("video_path"),
            audio_path=data.get("audio_path"),
            srt_path=data.get("srt_path"),
            note_path=data.get("note_path"),
            pdf_path=data.get("pdf_path"),
            mindmap_paths=list(data.get("mindmap_paths") or []),
            screenshot_paths=list(data.get("screenshot_paths") or []),
            node_statuses=node_statuses,
            llm_provider=data.get("llm_provider"),
            llm_model=data.get("llm_model"),
            asr_engine=data.get("asr_engine"),
            pdf_mode=data.get("pdf_mode") or "pypdf",
            extract_images=bool(data.get("extract_images", False)),
            output_language=data.get("output_language") or "zh",
            note_detail_level=data.get("note_detail_level") or "balanced",
            mindmap_formats=list(data.get("mindmap_formats") or ["xmind"]),
            queue_position=data.get("queue_position"),
            error=data.get("error"),
            created_at=_parse_datetime(data.get("created_at")) or datetime.now(),
            updated_at=_parse_datetime(data.get("updated_at")) or datetime.now(),
            finished_at=_parse_datetime(data.get("finished_at")),
        )

    @classmethod
    def from_db_row(cls, row: Any) -> "Task":
        """从数据库行(sqlite3.Row / dict)构造。

        按列名读取(不假设列顺序),JSON 列解包,datetime 解析。
        沿用基底安全解析风格。
        """
        def get_value(key: str, default: Any = None) -> Any:
            # 优先按列名访问(sqlite3.Row 或 dict)
            if hasattr(row, "keys"):
                try:
                    if key in row.keys():
                        return row[key]
                except Exception:
                    pass
            if isinstance(row, dict):
                return row.get(key, default)
            return default

        return cls(
            id=get_value("id", ""),
            source_type=get_value("source_type", "") or "",
            source_url=get_value("source_url"),
            title=get_value("title"),
            status=_coerce_status(get_value("status", TaskStatus.PENDING.value)),
            progress=int(get_value("progress", 0) or 0),
            video_path=get_value("video_path"),
            audio_path=get_value("audio_path"),
            srt_path=get_value("srt_path"),
            note_path=get_value("note_path"),
            pdf_path=get_value("pdf_path"),
            mindmap_paths=_safe_json_loads(get_value("mindmap_paths"), []),
            screenshot_paths=_safe_json_loads(get_value("screenshot_paths"), []),
            node_statuses=_safe_json_loads(get_value("node_statuses"), default_node_statuses()) or default_node_statuses(),
            llm_provider=get_value("llm_provider"),
            llm_model=get_value("llm_model"),
            asr_engine=get_value("asr_engine"),
            pdf_mode=get_value("pdf_mode") or "pypdf",
            extract_images=bool(get_value("extract_images", False)),
            output_language=get_value("output_language") or "zh",
            note_detail_level=get_value("note_detail_level") or "balanced",
            mindmap_formats=_safe_json_loads(get_value("mindmap_formats"), ["xmind"]) or ["xmind"],
            queue_position=get_value("queue_position"),
            error=get_value("error"),
            created_at=_parse_datetime(get_value("created_at")) or datetime.now(),
            updated_at=_parse_datetime(get_value("updated_at")) or datetime.now(),
            finished_at=_parse_datetime(get_value("finished_at")),
        )
