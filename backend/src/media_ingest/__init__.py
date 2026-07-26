"""media_ingest：媒体来源识别 + yt-dlp 下载 + ffmpeg 音频提取（spec media-ingest）。

对应 CONTRACT §6.1 接口契约，对外暴露：

- 来源识别：:class:`SourceType`、:class:`UploadedFile`、:func:`identify_source`
- 视频下载：:func:`download_video`（失败抛 :class:`DownloadError`、取消抛 :class:`IngestCancelled`）
- 音频提取：:func:`extract_audio`（失败抛 :class:`ExtractError`）
- 五种下载失败归类常量 ``DOWNLOAD_ERR_*``

DAG 的 ``download`` / ``extract_audio`` 节点（CONTRACT §5.1）直接调用本包；本地来源节点
由 DAG 标 ``skipped``，不会调用下载 / 提取。
"""
from .source import SourceType, UploadedFile, identify_source
from .downloader import (
    download_video,
    DownloadError,
    IngestCancelled,
    DOWNLOAD_ERR_INVALID_URL,
    DOWNLOAD_ERR_NEEDS_LOGIN,
    DOWNLOAD_ERR_NETWORK,
    DOWNLOAD_ERR_RISK_CONTROL,
    DOWNLOAD_ERR_TOOL_MISSING,
)
from .audio import extract_audio, ExtractError

__all__ = [
    # 来源识别
    "SourceType",
    "UploadedFile",
    "identify_source",
    # 视频下载
    "download_video",
    "DownloadError",
    "IngestCancelled",
    "DOWNLOAD_ERR_INVALID_URL",
    "DOWNLOAD_ERR_NEEDS_LOGIN",
    "DOWNLOAD_ERR_NETWORK",
    "DOWNLOAD_ERR_RISK_CONTROL",
    "DOWNLOAD_ERR_TOOL_MISSING",
    # 音频提取
    "extract_audio",
    "ExtractError",
]
