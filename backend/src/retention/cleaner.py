"""产物保留策略与过期清理引擎(vid2note v1 · design D9 / spec storage-retention / CONTRACT §6.7)。

职责
----
1. 五类产物(video/audio/srt/note/screenshot)各自独立的保留策略(permanent / 7d / 30d),
   策略来源:传入的 ``settings``(运行时设置快照或 ``retention.<kind>`` 字典),
   缺省时回退到 :data:`DEFAULT_RETENTION_POLICIES`( CONTRACT §3.2 建议)。
2. :func:`run_cleanup_scan` —— 周期性 + 启动时调用:
   - 按各自策略删过期产物(permanent 永不删);
   - 跳过未达终态(pending/running/processing)任务的产物;
   - 删后同步把 SQLite 中对应产物引用置空/移除(历史不再指向已删文件);
   - 顺带清理 ``data/temp/<task_id>/``(终态/孤儿任务的临时目录)。
3. :func:`cleanup_expired` —— 面向「定时器/启动钩子」的便捷入口,默认拼装 repo /
   data_root / settings 后委托给 :func:`run_cleanup_scan`,并支持注入 ``now`` 模拟
   系统时钟(单测用)。
4. :func:`cleanup_task_temp` —— cleanup 节点收尾时清空单个任务的 temp 目录。

设计说明(关键)
----------------
- **以文件系统为权威**:扫描直接遍历五类产物目录(``videos/`` … ``screenshots/``),
  以「文件 mtime」度量产物年龄(=「已存在多久」),与具体 Task dataclass 解耦,
  orphan 文件(任务记录已不存在)也能被回收。
- **任务终态判定走 repo**:retention 对仓库采用依赖倒置 —— 只依赖一个极简协议
  (``get_by_id`` / ``update``),通过 ``getattr`` 读 v1 产物字段
  (``video_path`` / ``audio_path`` / ``srt_path`` / ``note_path`` /
  ``mindmap_paths`` / ``screenshot_paths``)。这样在 v1 schema(task 1.3/1.4)落地
  前后均可用,单测以 FakeRepo 验证;真实仓库落地后无需改本模块。
- **SQLite 引用同步为 best-effort**:删除产物是硬要求,引用同步次之;真实仓库列
  缺失时只记错误日志、不中断整个扫描。
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional, Protocol, runtime_checkable

# 复用内核统一日志(允许基底式 try/except ImportError 双写,见 CONTRACT §0.1)。
try:  # pragma: no cover - 仅在内核未就绪时走兜底
    from src.core.kernel import logger as _kernel_logger
except Exception:  # pragma: no cover
    import logging

    _kernel_logger = logging.getLogger("retention")

logger = _kernel_logger


# ---------------------------------------------------------------------------
# 常量与枚举
# ---------------------------------------------------------------------------


class RetentionPolicy(str, Enum):
    """五类产物各自可选的保留策略(规范术语保留英文)。"""

    PERMANENT = "permanent"  # 永久保留,清理扫描永不删除
    DAYS_7 = "7d"  # 保留 7 天
    DAYS_30 = "30d"  # 保留 30 天


#: 五类产物 kind(与 CONTRACT §6.7 / spec 一致;mindmap 与 note 同放 notes/)。
PRODUCT_KINDS: list[str] = ["video", "audio", "srt", "note", "screenshot"]

#: kind → 落盘目录名(CONTRACT §2.1)。
KIND_DIR: dict[str, str] = {
    "video": "videos",
    "audio": "audio",
    "srt": "srt",
    "note": "notes",
    "screenshot": "screenshots",
}

#: kind → 顶层标量产物字段(单文件引用;相对 DATA_ROOT 的 POSIX 路径)。
KIND_SCALAR_FIELD: dict[str, str] = {
    "video": "video_path",
    "audio": "audio_path",
    "srt": "srt_path",
    "note": "note_path",
}

#: kind → 列表型产物字段(多文件引用)。
#: 注:思维导图与笔记同放 notes/ 目录,故 ``note`` 类清理后需同时维护 mindmap_paths。
KIND_LIST_FIELDS: dict[str, list[str]] = {
    "note": ["mindmap_paths"],
    "screenshot": ["screenshot_paths"],
}

#: 首次启动 / settings 缺失时的默认保留策略(CONTRACT §3.2 建议)。
DEFAULT_RETENTION_POLICIES: dict[str, RetentionPolicy] = {
    "video": RetentionPolicy.DAYS_7,
    "audio": RetentionPolicy.DAYS_7,
    "srt": RetentionPolicy.DAYS_30,
    "note": RetentionPolicy.PERMANENT,
    "screenshot": RetentionPolicy.DAYS_30,
}

#: 任务终态集合(只有终态任务的产物才允许被清理;规范术语保留英文)。
TERMINAL_STATUSES: set[str] = {"completed", "failed", "cancelled"}

#: 未达终态(活跃)任务集合 —— 这类任务的产物 MUST 跳过。
#: 含基底历史值 ``processing`` 以兼容旧库。
ACTIVE_STATUSES: set[str] = {"pending", "running", "processing", "queued"}

#: 一天对应的秒数。
_DAY_SECONDS = 86_400


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class CleanupReport:
    """一次清理扫描的结果汇总。"""

    #: 被删除的产物相对路径列表(相对 DATA_ROOT 的 POSIX 路径;temp 目录以 ``/`` 结尾)。
    deleted: list[str] = field(default_factory=list)
    #: 累计回收字节数(产物 + temp)。
    freed_bytes: int = 0
    #: 因所属任务未达终态而跳过的文件 / 目录计数。
    skipped_active: int = 0
    #: best-effort 引用同步过程中发生的错误(不中断扫描)。
    errors: list[str] = field(default_factory=list)

    def merge(self, other: "CleanupReport") -> None:
        """合并另一份报告(内部累加用)。"""
        self.deleted.extend(other.deleted)
        self.freed_bytes += other.freed_bytes
        self.skipped_active += other.skipped_active
        self.errors.extend(other.errors)


@dataclass
class _StatusLookup:
    """仓库查询某 task_id 的结果缓存项。"""

    status: Optional[str]  # 规范化后的小写状态字面量;None 表示未知/不在库
    in_db: bool  # 该 task_id 是否在 SQLite 中存在记录
    terminal: bool  # 是否处于终态(只有 in_db=True 时有意义)


# ---------------------------------------------------------------------------
# 仓库协议(依赖倒置:retention 不直接依赖 Task dataclass)
# ---------------------------------------------------------------------------


@runtime_checkable
class _RepoLike(Protocol):
    """retention 所需的最小仓库协议(生产态由 TaskRepository 满足)。"""

    def get_by_id(self, task_id: str) -> Optional[Any]: ...

    def update(self, task_id: str, **kwargs: Any) -> bool: ...


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _default_data_root() -> Path:
    """默认 DATA_ROOT:优先环境变量,其次 backend/data。"""
    env = os.environ.get("DATA_ROOT")
    if env:
        return Path(env)
    # cleaner.py 位于 backend/src/retention/cleaner.py → parents[2] = backend/
    return Path(__file__).resolve().parents[2] / "data"


def _default_repo() -> Any:
    """惰性构造默认仓库(内核 TaskRepository)。"""
    try:
        from src.core.kernel import TaskRepository
    except ImportError:  # pragma: no cover - 内核未就绪兜底
        from src.db.task_repository import TaskRepository
    return TaskRepository()


def _rel(data_root: Path, path: Path) -> str:
    """转换为相对 DATA_ROOT 的 POSIX 路径(落库 / 报告统一形态)。"""
    try:
        return path.relative_to(data_root).as_posix()
    except ValueError:
        return path.as_posix()


def _coerce_policy(value: Any, default: RetentionPolicy) -> RetentionPolicy:
    """把任意输入安全收敛为 RetentionPolicy;非法值回退 default(不抛错)。"""
    if value is None:
        return default
    try:
        return RetentionPolicy(str(value).strip())
    except Exception:
        logger.warning("非法保留策略值 %r,回退默认 %s", value, default.value)
        return default


def _extract_policies(settings: Any) -> dict[str, RetentionPolicy]:
    """从多种 settings 形态抽取五类策略。

    支持的形态:
    - ``None`` → 全部走默认;
    - ``dict``:优先 ``retention.<kind>`` 键(CONTRACT §3.2 settings 命名空间),
      兼容裸 ``<kind>`` 键;
    - 带方法 ``get_setting(key)`` 的对象(未来 SettingsRepository);
    - 带属性 ``retention``(dict)的对象。
    非法取值在 settings 校验层应已拒绝;此处对残留非法值回退默认,保证扫描不崩。
    """
    raw: dict[str, Any] = {}
    if settings is None:
        pass
    elif isinstance(settings, dict):
        raw = settings
    elif callable(getattr(settings, "get_setting", None)):
        for kind in PRODUCT_KINDS:
            try:
                raw[f"retention.{kind}"] = settings.get_setting(f"retention.{kind}")
            except Exception:
                pass
    elif isinstance(getattr(settings, "retention", None), dict):
        raw = {
            f"retention.{k}": v for k, v in settings.retention.items()  # type: ignore[union-attr]
        }
    else:
        # 尝试 retention_<kind> 形式的属性
        for kind in PRODUCT_KINDS:
            attr = f"retention_{kind}"
            if hasattr(settings, attr):
                raw[f"retention.{kind}"] = getattr(settings, attr)

    policies: dict[str, RetentionPolicy] = {}
    for kind in PRODUCT_KINDS:
        default = DEFAULT_RETENTION_POLICIES[kind]
        val = raw.get(f"retention.{kind}", raw.get(kind))
        policies[kind] = _coerce_policy(val, default)
    return policies


def _policy_days(policy: RetentionPolicy) -> Optional[int]:
    """策略对应的天数;permanent → None(永不删)。"""
    if policy is RetentionPolicy.DAYS_7:
        return 7
    if policy is RetentionPolicy.DAYS_30:
        return 30
    return None


def _is_expired(file_mtime: float, now: datetime, policy: RetentionPolicy) -> bool:
    """判定文件是否过期:年龄 >= 保留天数(边界含等号,匹配「存在 N 天以上」语义)。"""
    days = _policy_days(policy)
    if days is None:
        return False  # permanent 永不删
    age_seconds = now.timestamp() - file_mtime
    if age_seconds <= 0:
        return False  # 文件时间戳不晚于 now(未来文件/同时)不判过期
    return age_seconds >= days * _DAY_SECONDS


def _normalize_status(task: Any) -> _StatusLookup:
    """从任务对象读 status,返回规范化查找结果。"""
    if task is None:
        return _StatusLookup(status=None, in_db=False, terminal=False)
    status = getattr(task, "status", None)
    val = getattr(status, "value", status)  # 兼容 Enum / 裸字面量
    val = str(val).strip().lower() if val is not None else None
    terminal = val in TERMINAL_STATUSES
    return _StatusLookup(status=val, in_db=True, terminal=terminal)


def _as_list(val: Any) -> Optional[list[str]]:
    """把字段值(可能是 JSON 字符串 / list / None)规整为 list;None 表示从未设置。"""
    if val is None:
        return None
    if isinstance(val, list):
        return [str(x) for x in val]
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except Exception:
            pass
        return [s]
    # tuple / 其它可迭代
    try:
        return [str(x) for x in val]
    except Exception:
        return None


def _path_exists(data_root: Path, rel_path: Any) -> bool:
    """相对路径(或绝对路径)指向的文件是否仍存在。"""
    if not rel_path:
        return False
    p = Path(rel_path)
    if not p.is_absolute():
        p = data_root / p
    return p.exists()


def _count_files(path: Path) -> int:
    """统计目录下文件数量(递归)。"""
    if not path.exists():
        return 0
    return sum(1 for f in path.rglob("*") if f.is_file())


def _dir_size(path: Path) -> int:
    """目录总字节数(递归);不存在返回 0。"""
    path = Path(path)
    if not path.exists():
        return 0
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def _safe_unlink(path: Path) -> bool:
    """删除单个文件,容错。"""
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except Exception as e:
        logger.warning("删除文件失败 %s: %s", path, e)
        return False


def _safe_rmtree(path: Path) -> bool:
    """递归删除目录,容错。"""
    try:
        shutil.rmtree(path)
        return True
    except FileNotFoundError:
        return False
    except Exception as e:
        logger.warning("删除目录失败 %s: %s", path, e)
        return False


def _child_task_dirs(kind_dir: Path) -> list[Path]:
    """某类产物目录下的所有 task_id 一级子目录。"""
    if not kind_dir.exists():
        return []
    return [p for p in kind_dir.iterdir() if p.is_dir()]


# ---------------------------------------------------------------------------
# SQLite 引用同步
# ---------------------------------------------------------------------------


def _reconcile_references(
    repo: Any,
    task_id: str,
    kinds: set[str],
    data_root: Path,
    report: CleanupReport,
) -> None:
    """删除产物后,把任务记录里指向「已不存在文件」的引用置空/移除。

    - 标量字段(``video_path`` 等):若指向的文件已不存在 → 置 None;
    - 列表字段(``mindmap_paths`` / ``screenshot_paths``):过滤掉已不存在的路径。
    更新失败(best-effort)只记错误日志,不中断扫描。
    """
    try:
        task = repo.get_by_id(task_id)
    except Exception as e:
        report.errors.append(f"读取任务 {task_id} 失败: {e}")
        return
    if task is None:
        # orphan 文件(任务记录已不存在),无引用可清。
        return

    updates: dict[str, Any] = {}

    # 标量字段
    for kind in kinds:
        field_name = KIND_SCALAR_FIELD.get(kind)
        if not field_name:
            continue
        current = getattr(task, field_name, None)
        if current and not _path_exists(data_root, current):
            updates[field_name] = None

    # 列表字段
    list_field_names: set[str] = set()
    for kind in kinds:
        list_field_names.update(KIND_LIST_FIELDS.get(kind, []))
    for field_name in list_field_names:
        current = _as_list(getattr(task, field_name, None))
        if current is None:
            continue
        remaining = [p for p in current if _path_exists(data_root, p)]
        if remaining != current:
            updates[field_name] = remaining

    if not updates:
        return

    try:
        repo.update(task_id, **updates)
        logger.info(
            "已同步任务 %s 的产物引用(置空/移除 %d 项)", task_id, len(updates)
        )
    except Exception as e:
        # 真实仓库列缺失(如 v1 schema 未落地)会走到这里:不中断扫描。
        report.errors.append(f"更新任务 {task_id} 产物引用失败: {e}")
        logger.warning("更新任务 %s 产物引用失败: %s", task_id, e)


# ---------------------------------------------------------------------------
# temp 目录清理
# ---------------------------------------------------------------------------


def cleanup_task_temp(task_id: str, data_root: Any = None) -> int:
    """清空 ``data/temp/<task_id>/``(cleanup 节点收尾调用)。

    Args:
        task_id: 任务 ID。
        data_root: 产物根目录;None 时取默认。

    Returns:
        实际回收的字节数。
    """
    root = Path(data_root) if data_root is not None else _default_data_root()
    task_temp = root / "temp" / task_id
    if not task_temp.exists():
        return 0
    freed = _dir_size(task_temp)
    if _safe_rmtree(task_temp):
        logger.info("已清空任务 %s 的临时目录(%d 字节)", task_id, freed)
        return freed
    return 0


def _cleanup_temp(
    data_root: Path,
    repo: Any,
    status_cache: dict[str, _StatusLookup],
    report: CleanupReport,
) -> None:
    """扫描时顺带清理 temp:仅删终态/孤儿任务的 temp;活跃任务 temp 保留。"""
    temp_root = data_root / "temp"
    if not temp_root.exists():
        return

    for entry in list(temp_root.iterdir()):
        if entry.is_dir():
            task_id = entry.name
            st = status_cache.get(task_id)
            if st is None:
                try:
                    st = _normalize_status(repo.get_by_id(task_id))
                except Exception:
                    st = _StatusLookup(status=None, in_db=False, terminal=False)
                status_cache[task_id] = st
            # 活跃任务(在库且未终态)的 temp 保留;终态/孤儿任务的 temp 回收。
            if st.in_db and not st.terminal:
                report.skipped_active += 1
                continue
            size = _dir_size(entry)
            if _safe_rmtree(entry):
                report.deleted.append(_rel(data_root, entry) + "/")
                report.freed_bytes += size
        elif entry.is_file():
            # temp 顶层散落文件(不应出现):直接清掉,字节计入回收。
            try:
                size = entry.stat().st_size
            except OSError:
                size = 0
            if _safe_unlink(entry):
                report.deleted.append(_rel(data_root, entry))
                report.freed_bytes += size


# ---------------------------------------------------------------------------
# 公共 API:扫描清理
# ---------------------------------------------------------------------------


def run_cleanup_scan(
    repo: Any,
    data_root: Any,
    settings: Any = None,
    clock: Callable[[], datetime] = datetime.now,
) -> CleanupReport:
    """按五类各自策略扫描并清理过期产物。

    Args:
        repo: 仓库(满足 :class:`_RepoLike` 协议);用于查任务终态、删后同步引用。
        data_root: 产物根目录(DATA_ROOT)。
        settings: 保留策略来源(dict / SettingsSnapshot / None);None 用默认。
        clock: 系统时钟注入(默认 :func:`datetime.now`);单测可快进。

    Returns:
        :class:`CleanupReport`。

    规则(CONTRACT §6.7 / spec storage-retention):
        - permanent 永不删;
        - 跳过未达终态(pending/running/…)任务的产物;
        - 删除后同步置空 SQLite 中对应产物引用;
        - temp 目录:终态/孤儿任务的 temp 一并回收,活跃任务的 temp 保留。
    """
    root = Path(data_root)
    now = clock()
    policies = _extract_policies(settings)
    report = CleanupReport()
    status_cache: dict[str, _StatusLookup] = {}
    affected_tasks: dict[str, set[str]] = {}  # task_id → 被删产物的 kind 集合

    def lookup(task_id: str) -> _StatusLookup:
        if task_id in status_cache:
            return status_cache[task_id]
        try:
            st = _normalize_status(repo.get_by_id(task_id))
        except Exception:
            st = _StatusLookup(status=None, in_db=False, terminal=False)
        status_cache[task_id] = st
        return st

    # 1) 五类产物按各自策略清理
    for kind in PRODUCT_KINDS:
        policy = policies[kind]
        kind_dir = root / KIND_DIR[kind]
        for task_dir in _child_task_dirs(kind_dir):
            task_id = task_dir.name
            st = lookup(task_id)
            if st.in_db and not st.terminal:
                # 未终态任务:跳过该任务此类的全部产物。
                report.skipped_active += _count_files(task_dir)
                continue
            # 终态 / orphan:按年龄逐文件判定
            for f in task_dir.rglob("*"):
                if not f.is_file():
                    continue
                try:
                    mtime = f.stat().st_mtime
                    size = f.stat().st_size
                except OSError:
                    continue
                if _is_expired(mtime, now, policy):
                    if _safe_unlink(f):
                        report.deleted.append(_rel(root, f))
                        report.freed_bytes += size
                        affected_tasks.setdefault(task_id, set()).add(kind)

    # 2) 清掉因删除而变空的 task_id 子目录(保持产物目录整洁)
    for kind in PRODUCT_KINDS:
        kind_dir = root / KIND_DIR[kind]
        for task_dir in _child_task_dirs(kind_dir):
            if _count_files(task_dir) == 0:
                # 仅删空目录本身(rmtree 以防有空子目录残留)
                _safe_rmtree(task_dir)

    # 3) temp 目录清理(终态/孤儿任务)
    _cleanup_temp(root, repo, status_cache, report)

    # 4) 同步 SQLite 产物引用(历史不再指向已删文件)
    for task_id, kinds in affected_tasks.items():
        _reconcile_references(repo, task_id, kinds, root, report)

    logger.info(
        "清理扫描完成:删除 %d 项,回收 %d 字节,跳过活跃任务产物 %d 项,错误 %d 条",
        len(report.deleted),
        report.freed_bytes,
        report.skipped_active,
        len(report.errors),
    )
    return report


def cleanup_expired(
    now: Optional[datetime] = None,
    repo: Any = None,
    data_root: Any = None,
    settings: Any = None,
) -> CleanupReport:
    """便捷清理入口(定时器 / 启动钩子调用)。

    Args:
        now: 注入的「当前时间」;None 用 :func:`datetime.now`。单测可快进以模拟过期。
        repo: 仓库;None 用默认内核 TaskRepository。
        data_root: 产物根;None 取 DATA_ROOT 环境变量或 backend/data。
        settings: 保留策略来源;None 时尝试从 settings 表读取,再回退默认。

    Returns:
        :class:`CleanupReport`。
    """
    if repo is None:
        repo = _default_repo()
    if data_root is None:
        data_root = _default_data_root()
    if settings is None:
        settings = _load_retention_settings(repo)
    clock: Callable[[], datetime] = (lambda: now) if now is not None else datetime.now
    return run_cleanup_scan(repo, data_root, settings, clock=clock)


def _load_retention_settings(repo: Any) -> Any:
    """尝试从 settings 表读取 retention.* 键;读不到(表/方法缺失)返回 None 走默认。"""
    raw: dict[str, Any] = {}
    try:
        if callable(getattr(repo, "get_all_settings", None)):
            result = repo.get_all_settings()
            if isinstance(result, dict):
                raw = result
            else:
                raw = {row[0]: row[1] for row in result}
        else:
            db = getattr(repo, "db", None)
            if db is not None:
                rows = db.fetchall("SELECT key, value FROM settings")
                raw = {row[0]: row[1] for row in rows}
    except Exception:
        # settings 表尚未建立(v1 schema 未落地)——回退默认策略。
        return None

    retention_raw = {k: v for k, v in raw.items() if str(k).startswith("retention.")}
    return retention_raw or None


__all__ = [
    "RetentionPolicy",
    "PRODUCT_KINDS",
    "KIND_DIR",
    "KIND_SCALAR_FIELD",
    "KIND_LIST_FIELDS",
    "DEFAULT_RETENTION_POLICIES",
    "TERMINAL_STATUSES",
    "ACTIVE_STATUSES",
    "CleanupReport",
    "cleanup_task_temp",
    "run_cleanup_scan",
    "cleanup_expired",
]
