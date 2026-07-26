"""ffmpeg 音频提取（spec media-ingest / CONTRACT §6.1）。

从视频产物提取 **16 kHz 单声道 WAV**，作为 ASR 步骤的输入（spec speech-to-text）。
本地音频来源由 DAG 跳过本节点（不调本函数）；视频无音轨或 ffmpeg 失败时抛中文
:class:`ExtractError`，**绝不产出空 / 损坏的音频产物**。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from .downloader import (
    IngestCancelled,
    _is_cancelled,
    _probe_duration_seconds,
    _to_rel,
)


class ExtractError(Exception):
    """音频提取失败异常（中文 ``message`` + ffmpeg stderr ``ffmpeg_summary``）。"""

    def __init__(self, message: str, ffmpeg_summary: str = ""):
        self.message = message
        self.ffmpeg_summary = ffmpeg_summary
        full = message if not ffmpeg_summary else f"{message}（{ffmpeg_summary}）"
        super().__init__(full)


def _tail(text: str, n: int = 600) -> str:
    """取 ffmpeg stderr 末尾摘要（压空白、限长），供错误信息展示。"""
    if not text:
        return ""
    cleaned = " ".join(text.split())
    return cleaned[-n:] if len(cleaned) > n else cleaned


def extract_audio(ctx, video_rel_path: str) -> str:
    """ffmpeg 从视频提取 16 kHz 单声道 WAV，登记音频产物，返回相对 ``DATA_ROOT`` 路径。

    Args:
        ctx: DAG ``NodeContext``（提供 ``product_path`` / ``data_root`` /
            ``register_product`` / ``emit_progress`` / ``emit_log`` / ``cancel``）。
        video_rel_path: 相对 ``DATA_ROOT`` 的视频产物路径（download 节点产出 / 本地视频上传）。

    Returns:
        相对 ``DATA_ROOT`` 的音频产物 POSIX 路径（如 ``audio/task_xxx/task_xxx.wav``）。

    Raises:
        ExtractError: 视频不存在 / 无音轨 / ffmpeg 非零退出 / 产物时长为 0。
        IngestCancelled: 提取被用户取消。
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ExtractError(
            "音频提取失败：未找到 ffmpeg，请确认容器内已安装 ffmpeg",
        )

    # 取消检查（CONTRACT §0.6）
    if _is_cancelled(ctx):
        raise IngestCancelled()

    # 解析视频绝对路径（输入为相对 DATA_ROOT 的产物路径）
    data_root = Path(getattr(ctx, "data_root", "") or "")
    video_path = Path(video_rel_path)
    if not video_path.is_absolute():
        video_path = data_root / video_path
    if not video_path.exists():
        raise ExtractError(f"音频提取失败：视频产物不存在（{video_rel_path}）")

    ctx.emit_log("info", f"开始提取音频：{video_rel_path}")
    ctx.emit_progress(5, "准备提取音频")

    out_path: Path = Path(ctx.product_path("audio", "wav"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    src_duration = _probe_duration_seconds(video_path)

    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(video_path),
        "-vn",                  # 丢弃视频流
        "-acodec", "pcm_s16le", # 16-bit PCM
        "-ar", "16000",         # 16 kHz（ASR 标准）
        "-ac", "1",             # 单声道
        str(out_path),
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired as exc:
        out_path.unlink(missing_ok=True)
        raise ExtractError(
            "音频提取失败：ffmpeg 执行超时", _tail(str(exc.stderr or "")),
        ) from exc
    except OSError as exc:
        out_path.unlink(missing_ok=True)
        raise ExtractError(
            f"音频提取失败：无法启动 ffmpeg（{exc}）",
        ) from exc

    if proc.returncode != 0:
        # 失败必清半成品，绝不产空损产物
        out_path.unlink(missing_ok=True)
        stderr = (proc.stderr or "")
        stderr_low = stderr.lower()
        summary = _tail(stderr)
        if "does not contain any stream" in stderr_low or "no audio" in stderr_low:
            raise ExtractError("音频提取失败：源视频不含可用的音轨", summary)
        raise ExtractError("音频提取失败：ffmpeg 返回非零退出码", summary)

    # 产物校验：可读 + 时长 > 0
    if not out_path.exists() or out_path.stat().st_size <= 0:
        out_path.unlink(missing_ok=True)
        raise ExtractError(
            "音频提取失败：ffmpeg 未产出有效音频文件", _tail(proc.stderr or ""),
        )
    wav_duration = _probe_duration_seconds(out_path)
    if not wav_duration or wav_duration <= 0:
        out_path.unlink(missing_ok=True)
        raise ExtractError(
            "音频提取失败：提取的音频时长为 0", _tail(proc.stderr or ""),
        )

    # 时长一致性：音频可能因静音尾部短于视频，故差异较大时仅告警、仍保留产物
    if src_duration and abs(wav_duration - src_duration) > max(2.0, src_duration * 0.1):
        ctx.emit_log(
            "warn",
            f"音频时长（{wav_duration:.1f}s）与源视频（{src_duration:.1f}s）差异较大，"
            "已保留产物供 ASR 使用",
        )

    rel = _to_rel(ctx, out_path)
    size = out_path.stat().st_size
    ctx.emit_progress(100, "音频提取完成")
    ctx.emit_log("ok", f"音频产物已登记：{rel}（{wav_duration:.1f}s，{size} 字节）")
    ctx.register_product("audio", rel, size)
    return rel
