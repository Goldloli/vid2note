"""实验性在线 bcut ASR 引擎。

该实现通过 HTTP 完成分片上传、创建任务和结果轮询。外部服务或协议可能变化，
调用失败时由 pipeline 按策略降级到本地 Whisper。
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter

try:  # urllib3 新旧版本参数名兼容
    from urllib3.util.retry import Retry
except ImportError:  # pragma: no cover
    from requests.packages.urllib3.util.retry import Retry

from . import asr_cache
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
)

_LOGGER = logging.getLogger("speech_to_text.bcut")
_SUPPORTED_FORMATS = {"flac", "m4a", "mp3", "wav"}


def _ext(path: str) -> str:
    return os.path.splitext(path)[1].lower().lstrip(".")


def _raise_for_status(resp: requests.Response, action: str) -> None:
    """把 HTTP 错误翻译成可供降级策略识别的 ``AsrError``。"""
    code = resp.status_code
    if code == 429:
        raise AsrError(
            f"{action}被限流（HTTP 429）",
            reason=REASON_RATE_LIMITED,
            engine="bcut",
            status_code=code,
        )
    if code in (401, 403):
        raise AsrError(
            f"{action}鉴权失败（HTTP {code}）",
            reason=REASON_AUTH_FAILED,
            engine="bcut",
            status_code=code,
        )
    if 400 <= code < 600:
        raise AsrError(
            f"{action}服务不可用（HTTP {code}）",
            reason=REASON_SERVICE_UNAVAILABLE,
            engine="bcut",
            status_code=code,
        )


def _build_session() -> requests.Session:
    """带有限重试的 Session：对 429/5xx 自动重试（连接复用）。

    重试由 urllib3 在底层执行；用尽后仍按 ``_raise_for_status`` 抛结构化 ``AsrError``
    触发 pipeline 降级（保留 vid2note 现有错误分类，不倒退）。
    """
    session = requests.Session()
    retry_kwargs = dict(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    try:
        retry = Retry(allowed_methods=frozenset(["GET", "PUT", "POST"]), **retry_kwargs)
    except TypeError:  # 旧 urllib3 用 method_whitelist
        retry = Retry(method_whitelist=frozenset(["GET", "PUT", "POST"]), **retry_kwargs)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


class _BcutClient:
    """bcut 在线 ASR HTTP 客户端。"""

    BASE = "https://member.bilibili.com/x/bcut/rubick-interface"
    HEADERS = {
        "User-Agent": "Bilibili/1.0.0 (https://www.bilibili.com)",
        "Content-Type": "application/json",
    }

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout
        self._session = _build_session()
        self.task_id: Optional[str] = None
        self._in_boss_key = None
        self._resource_id = None
        self._upload_id = None
        self._upload_urls: list[str] = []
        self._per_size = 0
        self._download_url = None

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.BASE}{path}"
        try:
            resp = self._session.post(
                url,
                data=json.dumps(payload),
                headers=self.HEADERS,
                timeout=self.timeout,
            )
        except requests.exceptions.Timeout as exc:
            raise AsrError(
                f"{path} 超时",
                reason=REASON_TIMEOUT,
                engine="bcut",
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise AsrError(
                f"{path} 网络错误：{exc}",
                reason=REASON_NETWORK,
                engine="bcut",
            ) from exc
        _raise_for_status(resp, path)
        try:
            return resp.json()
        except ValueError as exc:
            raise AsrError(
                f"{path} 响应非 JSON",
                reason=REASON_INVALID_RESPONSE,
                engine="bcut",
            ) from exc

    def upload(self, binary: bytes) -> None:
        data = self._post(
            "/resource/create",
            {
                "type": 2,
                "name": "audio.mp3",
                "size": len(binary),
                "ResourceFileType": "mp3",
                "model_id": "8",
            },
        ).get("data") or {}
        self._in_boss_key = data.get("in_boss_key")
        self._resource_id = data.get("resource_id")
        self._upload_id = data.get("upload_id")
        self._upload_urls = data.get("upload_urls") or []
        self._per_size = data.get("per_size") or len(binary)
        if not (self._in_boss_key and self._upload_urls):
            raise AsrError(
                "bcut 申请上传响应异常",
                reason=REASON_INVALID_RESPONSE,
                engine="bcut",
            )

        etags: list[str] = []
        for clip, upload_url in enumerate(self._upload_urls):
            start = clip * self._per_size
            end = (clip + 1) * self._per_size
            try:
                resp = self._session.put(
                    upload_url,
                    data=binary[start:end],
                    headers=self.HEADERS,
                    timeout=self.timeout,
                )
            except requests.exceptions.Timeout as exc:
                raise AsrError(
                    "bcut 分片上传超时",
                    reason=REASON_TIMEOUT,
                    engine="bcut",
                ) from exc
            except requests.exceptions.RequestException as exc:
                raise AsrError(
                    f"bcut 分片上传网络错误：{exc}",
                    reason=REASON_NETWORK,
                    engine="bcut",
                ) from exc
            _raise_for_status(resp, "bcut 分片上传")
            etags.append(resp.headers.get("Etag", ""))

        commit = self._post(
            "/resource/create/complete",
            {
                "InBossKey": self._in_boss_key,
                "ResourceId": self._resource_id,
                "Etags": ",".join(etags),
                "UploadId": self._upload_id,
                "model_id": "8",
            },
        ).get("data") or {}
        self._download_url = commit.get("download_url")
        if not self._download_url:
            raise AsrError(
                "bcut 提交上传响应异常",
                reason=REASON_INVALID_RESPONSE,
                engine="bcut",
            )

    def create_task(self) -> str:
        data = self._post(
            "/task",
            {"resource": self._download_url, "model_id": "8"},
        ).get("data") or {}
        self.task_id = data.get("task_id")
        if not self.task_id:
            raise AsrError(
                "bcut 创建任务响应异常",
                reason=REASON_INVALID_RESPONSE,
                engine="bcut",
            )
        return self.task_id

    def result(self, task_id: Optional[str] = None) -> dict:
        url = f"{self.BASE}/task/result"
        try:
            resp = self._session.get(
                url,
                params={"model_id": 7, "task_id": task_id or self.task_id},
                headers=self.HEADERS,
                timeout=self.timeout,
            )
        except requests.exceptions.Timeout as exc:
            raise AsrError(
                "bcut 查询结果超时",
                reason=REASON_TIMEOUT,
                engine="bcut",
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise AsrError(
                f"bcut 查询结果网络错误：{exc}",
                reason=REASON_NETWORK,
                engine="bcut",
            ) from exc
        _raise_for_status(resp, "bcut 查询结果")
        try:
            return resp.json()["data"]
        except (ValueError, KeyError) as exc:
            raise AsrError(
                "bcut 查询结果响应异常",
                reason=REASON_INVALID_RESPONSE,
                engine="bcut",
            ) from exc


class BcutEngine(AsrEngine):
    """实验性在线 bcut 引擎。"""

    name = "bcut"

    def __init__(
        self,
        timeout: float = 120.0,
        query_interval: float = 1.0,
        query_max_wait: float = 600.0,
        cache_enabled: bool = True,
        cache_dir: Optional[str] = None,
        max_retries: int = 2,
    ) -> None:
        self.timeout = timeout
        self.query_interval = max(0.5, float(query_interval))
        self.query_max_wait = float(query_max_wait)
        self.cache_enabled = bool(cache_enabled)
        self.cache_dir = cache_dir
        self.max_retries = max(0, int(max_retries))

    def transcribe(
        self,
        audio_path: str,
        on_progress: Optional[ProgressCallback] = None,
    ) -> list[Cue]:
        ext = _ext(audio_path)
        if ext not in _SUPPORTED_FORMATS:
            raise AsrError(
                f"不支持的音频格式：{ext or '(无后缀)'}，仅支持 {sorted(_SUPPORTED_FORMATS)}",
                reason=REASON_UNSUPPORTED_FORMAT,
                engine=self.name,
            )
        if not os.path.exists(audio_path):
            raise AsrError(
                f"音频文件不存在：{audio_path}",
                reason=REASON_INVALID_RESPONSE,
                engine=self.name,
            )

        with open(audio_path, "rb") as file:
            binary = file.read()

        # crc32 文件级缓存：同音频命中跳过上传+轮询（借鉴 社区 bcut 参考实现 BaseASR）
        key = asr_cache.cache_key(self.name, binary, lang="")
        if self.cache_enabled:
            cached = asr_cache.get(self.cache_dir, key)
            if cached is not None:
                return cached

        # 上传 + 轮询（带重试：bcut 间歇失败重试 max_retries 次，避免轻易降级本地慢引擎）
        last_exc: Optional[AsrError] = None
        for attempt in range(self.max_retries + 1):
            client = _BcutClient(self.timeout)
            try:
                if on_progress:
                    on_progress(15, "上传音频（bcut）")
                client.upload(binary)
                if on_progress:
                    on_progress(50, "提交转写任务（bcut）")
                client.create_task()
                if on_progress:
                    on_progress(65, "获取转写结果（bcut）")
                deadline = time.time() + self.query_max_wait
                interval = self.query_interval
                while True:
                    task_response = client.result()
                    if task_response.get("state") == 4:
                        cues = self._parse_result(task_response)
                        if self.cache_enabled:
                            asr_cache.put(self.cache_dir, key, cues)
                        return cues
                    if time.time() > deadline:
                        raise AsrError(
                            "bcut 转写轮询超时",
                            reason=REASON_TIMEOUT,
                            engine=self.name,
                        )
                    # 指数退避 + 抖动（起步 query_interval，上限 8s），替代固定 2s
                    time.sleep(min(interval, 8.0) + random.uniform(0, 0.3))
                    interval = min(interval * 2, 8.0)
            except AsrError as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    _LOGGER.info("bcut 失败（%s），重试 %d/%d", exc.reason, attempt + 1, self.max_retries)
                    continue
        raise last_exc if last_exc else AsrError(
            "bcut 转写失败", reason=REASON_INVALID_RESPONSE, engine=self.name
        )

    @staticmethod
    def _parse_result(task_response: dict) -> list[Cue]:
        result = task_response.get("result")
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except ValueError as exc:
                raise AsrError(
                    "bcut 结果 JSON 解析失败",
                    reason=REASON_INVALID_RESPONSE,
                    engine="bcut",
                ) from exc
        if not isinstance(result, dict):
            raise AsrError(
                "bcut 结果结构异常",
                reason=REASON_INVALID_RESPONSE,
                engine="bcut",
            )

        cues: list[Cue] = []
        for utterance in result.get("utterances") or []:
            text = (
                utterance.get("transcript")
                or utterance.get("text")
                or ""
            ).strip()
            if not text:
                continue
            cues.append(
                Cue(
                    start=_milliseconds_to_seconds(utterance.get("start_time")),
                    end=_milliseconds_to_seconds(utterance.get("end_time")),
                    text=text,
                )
            )
        if not cues:
            _LOGGER.info("bcut 转写无语音内容，返回空 Cue 列表（不伪造）")
        return cues


def _milliseconds_to_seconds(value) -> float:
    try:
        return float(value) / 1000.0
    except (TypeError, ValueError):
        return 0.0
