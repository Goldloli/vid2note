"""媒体来源识别（spec media-ingest / CONTRACT §6.1）。

把任务输入（在线链接 或 本地音视频文件）归一化为五种 :class:`SourceType` 之一，
驱动 DAG 的「下载 / 提取」跳过决策（见 CONTRACT §5.5）。

- 在线链接 → 按宿主域名区分 ``youtube`` / ``bilibili`` / ``direct``（直链）
- 本地上传 → 按扩展名（或 MIME）区分 ``local_video`` / ``local_audio``
- 既非已知平台链接、又非 http(s) 直链、且无本地文件 → 抛中文 ``ValueError``，
  任务即在创建阶段被拒绝（CONTRACT §4.1「无法识别→400 中文错误」）。
"""
from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


class SourceType(str, Enum):
    """媒体来源类型。

    枚举值（英文小写）直接落 SQLite ``tasks.source_type`` 列，并驱动 DAG 跳过规则；
    保留英文是 CONTRACT §0.3「规范术语保留英文」的要求。
    """

    YOUTUBE = "youtube"
    BILIBILI = "bilibili"
    DIRECT = "direct"
    LOCAL_VIDEO = "local_video"
    LOCAL_AUDIO = "local_audio"


# 本地视频文件扩展名（小写、不含点）——用于区分 local_video
_VIDEO_EXTS = {
    "mp4", "mkv", "mov", "webm", "avi", "flv", "wmv", "m4v",
    "mpg", "mpeg", "ts", "3gp", "ogv",
}
# 本地音频文件扩展名（小写、不含点）——用于区分 local_audio
_AUDIO_EXTS = {
    "mp3", "wav", "m4a", "flac", "aac", "ogg", "wma", "opus", "weba", "aiff",
}

# YouTube 已知宿主（含短链 youtu.be、音乐、无饼干域）
_YOUTUBE_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "youtu.be", "music.youtube.com", "youtube-nocookie.com",
}
# Bilibili 已知宿主（含短链 b23.tv 与国际站 bilibili.tv）
_BILIBILI_HOSTS = {
    "bilibili.com", "www.bilibili.com", "m.bilibili.com",
    "b23.tv", "bilibili.tv", "www.bilibili.tv",
}


@dataclass
class UploadedFile:
    """本地已上传文件的归一化描述。

    由 API 上传层把 multipart 文件流式落盘到 ``data/temp/<task_id>/`` 后构造，
    传入 :func:`identify_source` 用于判别本地来源类型。
    """

    abs_path: str        # 已落盘的绝对路径
    original_name: str   # 用户上传时的原始文件名（用于取扩展名 / MIME 兜底）
    mime: str            # 浏览器上报的 MIME（如 video/mp4）
    size_bytes: int      # 文件字节大小


def _host_of(url: str) -> str:
    """取 URL 宿主名（小写、去端口）；解析失败返回空串。"""
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return ""
    return (parsed.hostname or "").lower()


def _ext_of(name: str) -> str:
    """取文件名扩展名（小写、不含点）；无扩展名返回空串。"""
    return Path(name or "").suffix.lower().lstrip(".")


def _looks_like_url(text: str) -> bool:
    """粗判是否为 http(s) URL（用于区分「链接」与「纯文本」）。"""
    text = (text or "").strip()
    if not text:
        return False
    return text.lower().startswith(("http://", "https://"))


def _validate_public_url(url: str) -> None:
    """Reject credentials and obvious local-network SSRF targets by default."""
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise ValueError("无法识别的媒体来源：链接格式无效") from exc
    if parsed.username or parsed.password:
        raise ValueError("无法识别的媒体来源：链接不能包含用户名或密码")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("无法识别的媒体来源：链接缺少主机名")
    allow_private = os.environ.get("ALLOW_PRIVATE_URLS", "").strip().lower() in {
        "1", "true", "yes", "on"
    }
    if allow_private:
        return
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("出于安全原因，默认不允许下载本机地址")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if not address.is_global:
        raise ValueError("出于安全原因，默认不允许下载内网或保留地址")


def identify_source(source_url: Optional[str],
                    uploaded: Optional[UploadedFile]) -> SourceType:
    """识别五类媒体来源，无法识别时抛中文 ``ValueError``。

    判别优先级：

    1. **存在本地上传** → 按扩展名（无扩展名时退到 MIME 前缀）区分
       ``local_video`` / ``local_audio``；扩展名与 MIME 都不可识别 → 拒绝。
    2. **存在在线链接** → 必须 http(s)；按宿主域名区分
       ``youtube`` / ``bilibili``，其余合法 http(s) 链接视为 ``direct``。
    3. **两者皆无**（纯文本、不支持协议、空输入）→ 拒绝。

    Args:
        source_url: 用户粘贴的视频链接，可能为 ``None``。
        uploaded: 本地上传文件描述，可能为 ``None``。

    Returns:
        :class:`SourceType` 之一。

    Raises:
        ValueError: 无法识别来源（中文消息，供 API 直接回 400）。
    """
    # 1) 本地上传优先：上传了文件就按文件类型走，忽略可能同时填的链接
    if uploaded is not None:
        ext = _ext_of(uploaded.original_name or uploaded.abs_path)
        mime = (uploaded.mime or "").lower()
        if ext in _VIDEO_EXTS or mime.startswith("video/"):
            return SourceType.LOCAL_VIDEO
        if ext in _AUDIO_EXTS or mime.startswith("audio/"):
            return SourceType.LOCAL_AUDIO
        bad = ext or "未知"
        raise ValueError(
            f"无法识别的媒体来源：不支持的本地文件类型「.{bad}」，"
            "仅支持常见视频（mp4/mkv/mov/webm 等）或音频（mp3/wav/m4a/flac 等）"
        )

    # 2) 在线链接
    if source_url:
        url = source_url.strip()
        if not _looks_like_url(url):
            raise ValueError(
                "无法识别的媒体来源：仅支持 http/https 视频链接或本地音视频文件"
            )
        if len(url) > 4096:
            raise ValueError("无法识别的媒体来源：链接过长")
        _validate_public_url(url)
        host = _host_of(url)
        if host in _YOUTUBE_HOSTS:
            return SourceType.YOUTUBE
        if host in _BILIBILI_HOSTS:
            return SourceType.BILIBILI
        # 非已知平台但仍是合法 http(s) 链接 → 直链（yt-dlp 尝试下载）
        return SourceType.DIRECT

    # 3) 既无文件又无链接 → 拒绝
    raise ValueError("无法识别的媒体来源：未提供链接或本地文件")
