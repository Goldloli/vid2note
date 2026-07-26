"""yt-dlp 整段最高画质下载（spec media-ingest / CONTRACT §6.1）。

职责：

- 用 yt-dlp 下载**整段完整视频**（``noplaylist``、不抓官方字幕），选**最高画质**；
  需要合并独立音视频流时自动合并为 mp4（``merge_output_format`` + ffmpeg）。
- **Bilibili 登录态**：当且仅当来源为 bilibili 且 cookie 同时含
  ``SESSDATA`` / ``bili_jct`` / ``DedeUserID`` 三项非空字段时，以登录态下载高画质；
  缺 / 部分缺 / 已失效 → 降级免登录画质并产出明确提示；cookie **仅用于 bilibili**，
  MUST NOT 外泄到 YouTube / 直链等其它来源的下载请求。
- 仅在产物**可读且时长 > 0** 时登记视频产物（相对 ``DATA_ROOT`` 的路径 + 字节大小）。
- 下载失败归类为五种 ``kind``（链接无效 / 需登录 / 网络 / 风控 / 工具缺失）并抛中文
  :class:`DownloadError`，供 DAG 标 failed、API 回可读错误。
- 下载期间经 ``ctx.emit_progress`` / ``ctx.emit_log`` 推送进度（供 SSE），并周期性响应
  ``ctx.cancel`` 取消信号（被取消抛 :class:`IngestCancelled`，DAG 据此丢弃半成品）。

设计要点（design D9「临时隔离」）：

- 中间分片（.part / .Frag 等）一律写 ``ctx.work_temp``（``data/temp/<task_id>/``）；
  校验通过后才把最终文件搬到 ``ctx.product_path('video','mp4')``（``videos/<tid>/``），
  失败 / 取消不留半成品于产物目录，便于「干净临时工作区重试」（spec media-ingest）。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

from .source import SourceType

# --------------------------------------------------------------------------- #
# 失败归类常量（落 DownloadError.kind；规范术语保留英文）
# --------------------------------------------------------------------------- #
DOWNLOAD_ERR_INVALID_URL = "invalid_url"       # 链接无效：不存在 / 已删除 / 无法解析
DOWNLOAD_ERR_NEEDS_LOGIN = "needs_login"       # 需登录：会员专享 / 需登录可见
DOWNLOAD_ERR_NETWORK = "network"               # 网络：中断 / 超时 / DNS
DOWNLOAD_ERR_RISK_CONTROL = "risk_control"     # 平台风控：验证码 / 限流 / 反爬
DOWNLOAD_ERR_TOOL_MISSING = "tool_missing"     # 工具缺失：未装 yt-dlp 或 ffmpeg

# Bilibili 登录态三项必填 cookie 字段
_BILI_COOKIE_KEYS = ("SESSDATA", "bili_jct", "DedeUserID")

# 下载后用于定位「最终视频文件」的容器扩展名（小写含点）；用于过滤 .part 等中间文件
_MEDIA_EXTS = (".mp4", ".webm", ".mkv", ".m4a", ".m4v", ".mov", ".flv", ".ts", ".mpg", ".mpeg")


class DownloadError(Exception):
    """下载失败异常，携带归类 ``kind`` 与中文 ``message``。"""

    def __init__(self, kind: str, message: str):
        self.kind = kind
        self.message = message
        super().__init__(f"[{kind}] {message}")


class IngestCancelled(Exception):
    """下载 / 提取过程中被用户取消。

    DAG 捕获后把当前节点置 cancelled、丢弃本节点半成品、保留已 completed 产物
    （CONTRACT §0.6 / §5.2）。
    """


# --------------------------------------------------------------------------- #
# 工具可用性检查
# --------------------------------------------------------------------------- #
def _require_yt_dlp():
    """惰性导入 yt-dlp；缺失抛 ``tool_missing``（中文）。

    惰性导入保证本模块在未装 yt-dlp 的环境也能被 import（仅调用下载时才报缺工具）。
    """
    try:
        import yt_dlp  # type: ignore
        return yt_dlp
    except ImportError as exc:  # pragma: no cover - 依赖环境
        raise DownloadError(
            DOWNLOAD_ERR_TOOL_MISSING,
            "未找到 yt-dlp，请确认容器内已安装 yt-dlp",
        ) from exc


def _require_ffmpeg() -> None:
    """检查 ffmpeg 可执行（合并独立音视频流必需）；缺失抛 ``tool_missing``。"""
    if not shutil.which("ffmpeg"):
        raise DownloadError(
            DOWNLOAD_ERR_TOOL_MISSING,
            "未找到 ffmpeg，合并独立音视频流需要 ffmpeg，请确认容器内已安装",
        )


# --------------------------------------------------------------------------- #
# ffprobe 时长探测（用于产物校验）
# --------------------------------------------------------------------------- #
def _probe_duration_seconds(path: Path) -> Optional[float]:
    """用 ffprobe 读取媒体时长（秒）；ffprobe 缺失或读取失败返回 ``None``。"""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        proc = subprocess.run(
            [
                ffprobe, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True, text=True, timeout=60,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    raw = (proc.stdout or "").strip()
    if not raw or raw.upper() == "N/A":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _to_rel(ctx, abs_path: Path) -> str:
    """把产物绝对路径转成相对 ``DATA_ROOT`` 的 POSIX 路径（CONTRACT §0.4 落库约定）。

    NodeContext 提供 ``data_root``；极端情况下无法相对化时退化为纯文件名（不抛错）。
    """
    data_root = Path(getattr(ctx, "data_root", "") or "")
    try:
        if data_root:
            return abs_path.resolve().relative_to(data_root.resolve()).as_posix()
    except (ValueError, OSError):
        pass
    return Path(abs_path).name


# --------------------------------------------------------------------------- #
# 失败归类（yt-dlp 异常 → 五种 kind）
# --------------------------------------------------------------------------- #
# 已知的「网络」异常类型名（沿异常链匹配，跨 urllib / socket / requests 等）
_NETWORK_EXC_NAMES = {
    "ConnectionError", "TimeoutError", "ConnectionResetError",
    "ConnectionAbortedError", "ConnectionRefusedError",
    "gaierror", "timeout", "URLError", "SSLError",
}


def _classify_download_error(exc: Optional[BaseException]) -> str:
    """把 yt-dlp 抛出的异常归类到五种 ``kind`` 之一。

    yt-dlp 几乎把所有失败包成 ``yt_dlp.utils.DownloadError``，原始异常挂在其
    ``__cause__`` / ``__context__`` 链上。故先沿异常链找「网络」异常类型，再退化到
    对消息文本的中 / 英文关键字匹配；仍未命中默认归 ``invalid_url``（无法获取视频）。
    """
    if exc is None:
        return DOWNLOAD_ERR_INVALID_URL

    # 1) 沿异常链找已知「网络」异常类型
    cur: Optional[BaseException] = exc
    seen: set = set()
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        cls_name = type(cur).__name__
        if cls_name in _NETWORK_EXC_NAMES:
            return DOWNLOAD_ERR_NETWORK
        cur = cur.__cause__ or cur.__context__

    msg = (str(exc) or "").lower()

    # 2) 平台风控 / 验证码 / 限流（优先于「需登录」，因 YouTube 风控文案含 "sign in"）
    if any(k in msg for k in (
        "sign in to confirm", "not a bot", "captcha", "verify your age",
        "robot", "rate limit", "rate-limit", "429", "too many requests",
        "风控", "验证码", "人机",
    )):
        return DOWNLOAD_ERR_RISK_CONTROL

    # 3) 需登录 / 会员专享（"member" 覆盖 member-only / members-only / members only 等）
    if any(k in msg for k in (
        "member", "join this channel",
        "available to this user only", "private video", "requires login",
        "log in", "login required", "sign in", "会员", "需要登录", "登录",
    )):
        return DOWNLOAD_ERR_NEEDS_LOGIN

    # 4) 链接无效 / 视频不存在 / 不支持
    if any(k in msg for k in (
        "video unavailable", "not exist", "not found", "removed", "deleted",
        "is not a valid url", "no video formats", "unsupported url",
        "unable to extract", "404", "410", "视频不存在", "链接无效", "无法解析",
    )):
        return DOWNLOAD_ERR_INVALID_URL

    # 5) 网络关键字（兜底）
    if any(k in msg for k in (
        "connection", "timeout", "timed out", "name resolution",
        "name or service", "network is unreachable", "temporarily unreachable",
        "reset by peer", "ssl", "no route", "dns", "errno -2", "errno -3",
    )):
        return DOWNLOAD_ERR_NETWORK

    # 默认：无法获取视频 → 链接无效（保留原始消息供日志）
    return DOWNLOAD_ERR_INVALID_URL


_KIND_ZH = {
    DOWNLOAD_ERR_INVALID_URL: "链接无效：视频不存在或无法解析该链接",
    DOWNLOAD_ERR_NEEDS_LOGIN: "需要登录：该内容需要登录或会员权限，请在设置页配置对应平台的 cookie",
    DOWNLOAD_ERR_NETWORK: "网络错误：下载中断或超时，请检查网络后重试",
    DOWNLOAD_ERR_RISK_CONTROL: "平台风控：触发验证码或限流，请稍后重试或检查 cookie / 网络",
    DOWNLOAD_ERR_TOOL_MISSING: "工具缺失：容器内缺少 yt-dlp 或 ffmpeg",
}


def _humanize_kind(kind: str) -> str:
    """归类 → 中文可读消息。"""
    return _KIND_ZH.get(kind, "下载失败")


def _looks_like_login_failure(exc: BaseException) -> bool:
    """判断 Bilibili 登录态下载失败是否疑似 cookie 失效（用于决定是否免登录降级）。"""
    if _classify_download_error(exc) == DOWNLOAD_ERR_NEEDS_LOGIN:
        return True
    msg = (str(exc) or "").lower()
    # Bilibili cookie 失效常见特征：-799 校验失败 / 风险校验 / cookie 关键字
    return any(k in msg for k in ("cookie", "login", "登录", "会员", "-799", "风险校验", "风控"))


# --------------------------------------------------------------------------- #
# Bilibili cookie 处理
# --------------------------------------------------------------------------- #
def _bilibili_cookies_usable(cookies: Optional[dict]) -> bool:
    """判断 cookie dict 是否同时含三项非空 Bilibili 字段（缺一即视为无登录态）。"""
    if not cookies:
        return False
    return all(str(cookies.get(k, "") or "").strip() for k in _BILI_COOKIE_KEYS)


def _filter_bilibili_cookies(cookies: Optional[dict]) -> dict:
    """仅保留三项 Bilibili cookie 字段（剥离 dict 中可能携带的其它键，防外泄）。"""
    if not cookies:
        return {}
    return {k: str(cookies[k]).strip()
            for k in _BILI_COOKIE_KEYS
            if cookies.get(k) not in (None, "")}


# --------------------------------------------------------------------------- #
# 进度回调（供 SSE）
# --------------------------------------------------------------------------- #
def _is_cancelled(ctx) -> bool:
    """安全读取取消信号；ctx 无 cancel 接口时视为未取消。"""
    cancel = getattr(ctx, "cancel", None)
    checker = getattr(cancel, "is_cancelled", None)
    if callable(checker):
        return bool(checker())
    return False


def _make_progress_hook(ctx) -> Callable[[dict], None]:
    """构造 yt-dlp ``progress_hooks`` 回调：推 SSE 进度 + 响应取消。"""

    def _hook(d: dict) -> None:
        # 周期性取消检查（CONTRACT §0.6：被取消尽快抛、丢弃半成品）
        if _is_cancelled(ctx):
            raise IngestCancelled()
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0) or 0
            if total:
                pct = max(0, min(95, int(downloaded * 100 / total)))
                ctx.emit_progress(pct, f"下载中 {downloaded // 1024}/{total // 1024} KB")
        elif status == "finished":
            # 单文件下载完成（可能还需合并）；推进度，留余量给合并 / 校验
            ctx.emit_progress(95, "下载完成，准备合并 / 校验")
        elif status == "error":
            ctx.emit_log("error", "yt-dlp 子任务出错")

    return _hook


# --------------------------------------------------------------------------- #
# 下载后定位最终视频文件
# --------------------------------------------------------------------------- #
def _locate_downloaded(temp_dir: Path, stem: str) -> Optional[Path]:
    """在临时目录定位下载产物（合并后的最终视频文件）。

    yt-dlp 以 ``<stem>.%(ext)s`` 模板输出，合并后通常只剩一个 ``<stem>.mp4``；
    多个候选时取最大者（理论上 merge_output_format 生效后不会留未合并的中间流）。
    """
    candidates = [p for p in temp_dir.glob(f"{stem}.*")
                  if p.is_file() and p.suffix.lower() in _MEDIA_EXTS]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_size)


# --------------------------------------------------------------------------- #
# 主入口
# --------------------------------------------------------------------------- #
def download_video(ctx, source_url: str, source_type: SourceType,
                   cookies: Optional[dict] = None) -> str:
    """用 yt-dlp 下载整段最高画质视频，登记视频产物，返回相对 ``DATA_ROOT`` 的路径。

    Args:
        ctx: DAG ``NodeContext``（提供 ``product_path`` / ``work_temp`` / ``data_root``
            / ``register_product`` / ``emit_progress`` / ``emit_log`` / ``cancel``）。
        source_url: 在线视频链接。
        source_type: 来源类型；仅 ``youtube`` / ``bilibili`` / ``direct`` 应被调用，
            本地来源由 DAG 跳过本节点（CONTRACT §5.5）。
        cookies: Bilibili 登录 cookie（``SESSDATA`` / ``bili_jct`` / ``DedeUserID``）；
            **仅在 ``source_type`` 为 bilibili 时**注入，其它来源绝不附带。

    Returns:
        相对 ``DATA_ROOT`` 的视频产物 POSIX 路径（如 ``videos/task_xxx/task_xxx.mp4``）。

    Raises:
        DownloadError: 下载失败（含归类 ``kind`` 与中文 ``message``）。
        IngestCancelled: 下载被用户取消。
    """
    if source_type not in (SourceType.YOUTUBE, SourceType.BILIBILI, SourceType.DIRECT):
        # 调用方应已对本地来源跳过本节点；防御性拒绝
        raise DownloadError(
            DOWNLOAD_ERR_INVALID_URL,
            f"来源类型「{source_type.value}」无需下载，调用方应跳过下载节点",
        )

    yt_dlp = _require_yt_dlp()
    _require_ffmpeg()

    ctx.emit_log("info", f"开始下载：{source_url}")
    ctx.emit_progress(1, "初始化下载")

    # 产物路径（videos/<tid>/<base>.mp4）+ 临时工作区（data/temp/<tid>/）
    out_path: Path = Path(ctx.product_path("video", "mp4"))
    temp_dir: Path = Path(ctx.work_temp)
    temp_dir.mkdir(parents=True, exist_ok=True)
    stem = out_path.stem
    # 下载到临时区：分片与最终文件都先落 temp，校验通过后再搬到产物目录
    tmpl = str(temp_dir / f"{stem}.%(ext)s")

    base_opts = {
        # 整段最高画质：优先独立最高画质视频 + 最高音质音频，回退到单文件最高
        "format": "bestvideo*+bestaudio/best",
        # 需合并独立音视频流时自动合并为 mp4
        "merge_output_format": "mp4",
        "outtmpl": tmpl,
        "noplaylist": True,          # 整段单个视频，不展开播放列表
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 5,                # 可恢复网络错误由 yt-dlp 内部重试
        "fragment_retries": 5,
        "progress_hooks": [_make_progress_hook(ctx)],
        # 字幕一律走 ASR（spec speech-to-text）：MUST NOT 抓取官方字幕
        "writesubtitles": False,
        "writeautomaticsub": False,
    }

    # Bilibili cookie：仅本来源注入，其它来源绝不外泄
    is_bili = source_type is SourceType.BILIBILI
    if is_bili:
        if _bilibili_cookies_usable(cookies):
            base_opts["cookies"] = _filter_bilibili_cookies(cookies)
            ctx.emit_log("info", "已注入 Bilibili 登录 cookie，尝试登录态高画质下载")
        else:
            ctx.emit_log(
                "warn",
                "未配置完整 Bilibili cookie（需 SESSDATA / bili_jct / DedeUserID 三项），"
                "已降级为免登录画质；如需更高画质请在设置页补全 cookie",
            )

    # 尝试列表：Bilibili 登录态失败 → 免登录降级重试一次；其余来源只试一次
    attempts: List[Tuple[str, dict]] = [("免登录" if not is_bili else "登录态", base_opts)]
    if is_bili and "cookies" in base_opts:
        degraded = dict(base_opts)
        degraded.pop("cookies", None)
        degraded["progress_hooks"] = [_make_progress_hook(ctx)
                                      ]  # 独立 hook 实例，避免被前一次复用
        attempts.append(("免登录降级", degraded))

    produced: Optional[Path] = None
    last_exc: Optional[BaseException] = None
    for label, opts in attempts:
        # 清掉上一轮可能残留的同名产物 / 中间文件，保证干净重试
        for stale in temp_dir.glob(f"{stem}.*"):
            try:
                stale.unlink()
            except OSError:
                pass
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([source_url])
            produced = _locate_downloaded(temp_dir, stem)
            if produced is not None:
                break
            last_exc = RuntimeError("yt-dlp 未产出可识别的视频文件")
            ctx.emit_log("warn", f"{label}下载未产出文件")
        except IngestCancelled:
            raise
        except BaseException as exc:  # yt_dlp.utils.DownloadError 等
            last_exc = exc
            ctx.emit_log("warn", f"{label}下载失败：{exc}")
            # 仅 Bilibili 登录态疑似 cookie 失效时降级重试
            if is_bili and "cookies" in opts and _looks_like_login_failure(exc):
                ctx.emit_log(
                    "warn",
                    "Bilibili cookie 可能已失效，降级为免登录画质重试；"
                    "如需更高画质请在设置页重新粘贴 cookie",
                )
                continue
            break

    if produced is None:
        kind = _classify_download_error(last_exc)
        raise DownloadError(kind, f"{_humanize_kind(kind)}（{source_url}）")

    # 产物校验：可读 + 时长 > 0；不通过清理半成品并归类报错（防把试看片段 / 风控页面落盘）
    try:
        size = produced.stat().st_size
    except OSError as exc:
        raise DownloadError(
            DOWNLOAD_ERR_INVALID_URL, f"无法读取下载产物：{exc}",
        ) from exc
    duration = _probe_duration_seconds(produced)
    if size <= 0 or not duration or duration <= 0:
        produced.unlink(missing_ok=True)
        raise DownloadError(
            DOWNLOAD_ERR_INVALID_URL,
            "下载产物无效（文件为空或时长为 0），可能仅下载到试看片段或风控页面",
        )

    # 搬到产物目录（覆盖同名，支持干净重试）
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    if produced.resolve() != out_path.resolve():
        shutil.move(str(produced), str(out_path))

    rel = _to_rel(ctx, out_path)
    ctx.emit_progress(100, "下载完成")
    ctx.emit_log("ok", f"视频产物已登记：{rel}（{duration:.1f}s，{size} 字节）")
    ctx.register_product("video", rel, size)
    return rel
