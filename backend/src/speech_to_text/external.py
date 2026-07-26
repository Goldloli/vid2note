"""speech_to_text.external —— 外部 ASR HTTP endpoint 引擎（扩展位）。

设计依据：design D2 / spec speech-to-text / CONTRACT §6.2。

- endpoint 地址 MUST 来自配置项（``external_endpoint``），MUST NOT 硬编码。
- 以 ``multipart/form-data`` 把音频 POST 到 endpoint，接收其返回并转换为 ``Cue``。
- 响应解析保持宽松，兼容三类常见契约：
  1. ``{"cues": [{"start","end","text"}, ...]}`` / ``{"segments": ...}`` / ``{"utterances": ...}``
     —— 时间戳支持秒（number）或毫秒（``start_time``/``end_time``）。
  2. ``{"srt": "1\\n00:00:... --> ...\\n...\\n..."}`` —— 直接按 SRT 解析。
- 失败语义同在线引擎（429/5xx/超时/鉴权），统一抛 ``AsrError`` 供降级日志分类。
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import requests

from .engine import (
    REASON_AUTH_FAILED,
    REASON_INVALID_RESPONSE,
    REASON_NETWORK,
    REASON_RATE_LIMITED,
    REASON_SERVICE_UNAVAILABLE,
    REASON_TIMEOUT,
    REASON_UNSUPPORTED_FORMAT,
    AsrEngine,
    AsrError,
    Cue,
    ProgressCallback,
    parse_srt_to_cues,
)

_LOGGER = logging.getLogger("speech_to_text.external")


class ExternalAsrEngine(AsrEngine):
    """外部 HTTP ASR endpoint 引擎。

    Args:
        endpoint: HTTP endpoint 地址（**来自配置**，不得硬编码）；为空时引擎不可用。
        timeout: 请求超时（秒）。
        api_key: 可选鉴权令牌（以 ``Authorization: Bearer <key>`` 发送）。
        extra_headers: 额外静态请求头。
    """

    name = "external"

    def __init__(
        self,
        endpoint: str = "",
        timeout: float = 120.0,
        api_key: str = "",
        extra_headers: Optional[dict] = None,
    ) -> None:
        self.endpoint = (endpoint or "").strip()
        self.timeout = timeout
        self.api_key = api_key or ""
        self.extra_headers = extra_headers or {}

    def transcribe(self, audio_path: str, on_progress: Optional[ProgressCallback] = None) -> list[Cue]:
        if not self.endpoint:
            # spec：endpoint 地址 MUST 来自配置项；缺省即视为该引擎不可用
            raise AsrError(
                "未配置外部 ASR endpoint", reason=REASON_SERVICE_UNAVAILABLE, engine=self.name
            )
        if not os.path.exists(audio_path):
            raise AsrError(
                f"音频文件不存在：{audio_path}", reason=REASON_UNSUPPORTED_FORMAT, engine=self.name
            )

        headers = dict(self.extra_headers)
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        filename = os.path.basename(audio_path)
        if on_progress:
            on_progress(20, "上传音频至外部 endpoint")

        try:
            with open(audio_path, "rb") as f:
                resp = requests.post(
                    self.endpoint,
                    files={"audio": (filename, f, "application/octet-stream")},
                    headers=headers,
                    timeout=self.timeout,
                )
        except requests.exceptions.Timeout as e:
            raise AsrError("外部 endpoint 请求超时", reason=REASON_TIMEOUT, engine=self.name) from e
        except requests.exceptions.RequestException as e:
            raise AsrError(f"外部 endpoint 网络错误：{e}", reason=REASON_NETWORK, engine=self.name) from e

        if resp.status_code == 429:
            raise AsrError("外部 endpoint 限流（HTTP 429）", reason=REASON_RATE_LIMITED, engine=self.name, status_code=429)
        if resp.status_code in (401, 403):
            raise AsrError(
                f"外部 endpoint 鉴权失败（HTTP {resp.status_code}）",
                reason=REASON_AUTH_FAILED, engine=self.name, status_code=resp.status_code,
            )
        if 500 <= resp.status_code < 600:
            raise AsrError(
                f"外部 endpoint 服务不可用（HTTP {resp.status_code}）",
                reason=REASON_SERVICE_UNAVAILABLE, engine=self.name, status_code=resp.status_code,
            )
        if resp.status_code >= 400:
            raise AsrError(
                f"外部 endpoint 请求被拒（HTTP {resp.status_code}）",
                reason=REASON_SERVICE_UNAVAILABLE, engine=self.name, status_code=resp.status_code,
            )

        if on_progress:
            on_progress(85, "解析外部 endpoint 返回")
        return self._parse(resp)

    # ---------------- 响应解析 ---------------- #

    def _parse(self, resp: requests.Response) -> list[Cue]:
        ctype = (resp.headers.get("Content-Type") or "").lower()
        body = (resp.text or "").strip()
        # 1) 直接是 SRT 文本（content-type 非 JSON 且文本像 SRT）
        if "json" not in ctype and "-->" in body and body[0:1].isdigit():
            cues = parse_srt_to_cues(body)
            if cues:
                return cues
        try:
            data = resp.json()
        except ValueError as e:
            # 既非 JSON 也未能按 SRT 解析
            if "-->" in body:
                cues = parse_srt_to_cues(body)
                if cues:
                    return cues
            raise AsrError(
                "外部 endpoint 返回非 JSON 且无法按 SRT 解析",
                reason=REASON_INVALID_RESPONSE, engine=self.name,
            ) from e

        # 2) JSON 内含现成 SRT 串
        if isinstance(data, dict) and isinstance(data.get("srt"), str):
            cues = parse_srt_to_cues(data["srt"])
            if cues:
                return cues

        # 3) JSON 内含片段列表（cues / segments / utterances / data.xxx）
        seq = _extract_segments(data)
        if seq is None:
            raise AsrError(
                "外部 endpoint 响应无可识别的片段列表",
                reason=REASON_INVALID_RESPONSE, engine=self.name,
            )
        cues: list[Cue] = []
        for item in seq:
            if not isinstance(item, dict):
                continue
            text = _first_str(item, ("text", "transcript", "original_subtitle"))
            if not text:
                continue
            start = _first_seconds(item, ("start", "start_time", "begin"))
            end = _first_seconds(item, ("end", "end_time", "stop"))
            if end <= start:
                # 容错：end 缺失时用 start + 一点时长
                end = start + max(0.1, _first_seconds(item, ("duration",)) or 1.0)
            cues.append(Cue(start=start, end=end, text=text))
        if not cues:
            _LOGGER.info("外部 endpoint 转写无语音内容，返回空 Cue 列表（不伪造）")
        return cues


def _extract_segments(data):
    """从层级不一的 JSON 里挖出片段列表。"""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return None
    for key in ("cues", "segments", "utterances", "results"):
        v = data.get(key)
        if isinstance(v, list):
            return v
    inner = data.get("data")
    if isinstance(inner, dict):
        for key in ("cues", "segments", "utterances"):
            v = inner.get(key)
            if isinstance(v, list):
                return v
    return None


def _first_str(d: dict, keys) -> str:
    for k in keys:
        if k in d and d[k] is not None:
            return str(d[k]).strip()
    return ""


def _first_seconds(d: dict, keys) -> float:
    """取首个命中的时间戳；同时兼容秒与毫秒（>1000 视为毫秒）。"""
    for k in keys:
        if k in d:
            try:
                val = float(d[k])
            except (TypeError, ValueError):
                continue
            # 启发式：数值很大（>1000）且无小数 → 大概率毫秒
            if val > 1000 and val == int(val):
                return val / 1000.0
            return val
    return 0.0
