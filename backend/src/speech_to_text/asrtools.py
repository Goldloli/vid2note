"""speech_to_text.asrtools —— 在线 AsrTools 引擎（剪映 / 必剪）。

设计依据：design D2 / spec speech-to-text / CONTRACT §6.2。

实现思路（不引入 bk_asr 包，自行用 ``requests`` 实现）：
- ``JianYingASR``（剪映）：上传音频到字节跳动对象存储 → submit → query。
  其中签名 ``sign`` 由可配置的「签名服务」返回（默认 ``asrtools-update.bkfeng.top/sign``，
  与 AsrTools-main 一致），签名服务地址 MUST 可经配置覆盖、不得与功能逻辑耦合。
- ``BcutASR``（必剪）：B 站 rubick 接口，无需外部签名服务，分片上传 → create task → 轮询结果。

二者返回的 utterance 时间戳均为毫秒，本引擎统一换算为「秒」封装进 ``Cue``。

失败语义（供 pipeline 降级，spec「在线引擎降级与日志记录」）：
- HTTP 429 / 5xx → ``REASON_RATE_LIMITED`` / ``REASON_SERVICE_UNAVAILABLE``。
- 超时（含 ``Timeout`` / ``ConnectionError``）→ ``REASON_TIMEOUT`` / ``REASON_NETWORK``。
- 鉴权/签名失败 → ``REASON_AUTH_FAILED``。
- 响应结构异常 → ``REASON_INVALID_RESPONSE``。
均以 ``AsrError`` 抛出，携带 ``engine`` 名与失败原因。
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
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
)

_LOGGER = logging.getLogger("speech_to_text.asrtools")

# AsrTools 支持的音频格式（与 bk_asr/BaseASR 一致）
_SUPPORTED_FORMATS = {"flac", "m4a", "mp3", "wav"}


def _ext(path: str) -> str:
    return os.path.splitext(path)[1].lower().lstrip(".")


def _raise_for_status(resp: requests.Response, engine: str, action: str) -> None:
    """把 HTTP 错误统一翻译成带 reason 的 ``AsrError``（供降级日志分类）。"""
    code = resp.status_code
    if code == 429:
        raise AsrError(
            f"{action}被限流（HTTP 429）", reason=REASON_RATE_LIMITED, engine=engine, status_code=code
        )
    if code in (401, 403):
        raise AsrError(
            f"{action}鉴权失败（HTTP {code}）", reason=REASON_AUTH_FAILED, engine=engine, status_code=code
        )
    if 500 <= code < 600:
        raise AsrError(
            f"{action}服务不可用（HTTP {code}）",
            reason=REASON_SERVICE_UNAVAILABLE,
            engine=engine,
            status_code=code,
        )
    if 400 <= code < 500:
        raise AsrError(
            f"{action}请求被拒（HTTP {code}）",
            reason=REASON_SERVICE_UNAVAILABLE,
            engine=engine,
            status_code=code,
        )


# ============================== 剪映（JianYing） ============================== #
# 以下 AWS 签名实现按 AsrTools-main/bk_asr/JianYingASR.py 的算法自行重写。


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _aws_siging_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
    k_date = _hmac_sha256(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = _hmac_sha256(k_date, region)
    k_service = _hmac_sha256(k_region, service)
    return _hmac_sha256(k_service, "aws4_request")


def _aws_signature(
    secret_key: str,
    request_parameters: str,
    headers: dict,
    method: str = "GET",
    payload: str = "",
    region: str = "cn",
    service: str = "vod",
) -> str:
    canonical_querystring = request_parameters
    canonical_headers = "\n".join(f"{k}:{v}" for k, v in headers.items()) + "\n"
    signed_headers = ";".join(headers.keys())
    payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    canonical_request = (
        f"{method}\n/\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )
    amzdate = headers["x-amz-date"]
    datestamp = amzdate.split("T")[0]
    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{datestamp}/{region}/{service}/aws4_request"
    string_to_sign = (
        f"{algorithm}\n{amzdate}\n{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )
    signing_key = _aws_siging_key(secret_key, datestamp, region, service)
    return hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()


class _JianYingClient:
    """剪映字幕接口客户端（纯 HTTP，无第三方包）。"""

    BASE = "https://lv-pc-api-sinfonlinec.ulikecam.com"

    def __init__(self, sign_endpoint: str, timeout: float) -> None:
        self.sign_endpoint = sign_endpoint
        self.timeout = timeout
        self.tdid = f"{uuid.getnode():012d}"
        # 凭证 / 上传态
        self.access_key = self.secret_key = self.session_token = None
        self.store_uri = self.auth = self.upload_id = self.session_key = self.upload_hosts = None

    # ---- 签名服务 ---- #
    def _sign(self, url_path: str) -> tuple[str, str]:
        """经签名服务获取 ``sign`` 与 ``device-time``。"""
        current_time = str(int(time.time()))
        data = {
            "url": url_path,
            "current_time": current_time,
            "pf": "4",
            "appvr": "4.0.0",
            "tdid": self.tdid,
        }
        try:
            resp = requests.post(self.sign_endpoint, json=data, timeout=self.timeout)
        except requests.exceptions.Timeout as e:
            raise AsrError("签名服务超时", reason=REASON_TIMEOUT, engine="asrtools") from e
        except requests.exceptions.RequestException as e:
            raise AsrError(f"签名服务网络错误：{e}", reason=REASON_NETWORK, engine="asrtools") from e
        if resp.status_code != 200:
            _raise_for_status(resp, "asrtools", "签名服务")
        try:
            sign = resp.json().get("sign")
        except ValueError as e:
            raise AsrError("签名服务响应非 JSON", reason=REASON_INVALID_RESPONSE, engine="asrtools") from e
        if not sign:
            raise AsrError("签名服务未返回 sign", reason=REASON_AUTH_FAILED, engine="asrtools")
        return sign.lower(), current_time

    def _headers(self, device_time: str, sign: str) -> dict:
        return {
            "User-Agent": "Cronet/TTNetVersion:01594da2 2023-03-14 QuicVersion:46688bb4 2022-11-28",
            "appvr": "4.0.0",
            "device-time": str(device_time),
            "pf": "4",
            "sign": sign,
            "sign-ver": "1",
            "tdid": self.tdid,
        }

    # ---- 上传 ---- #
    def _upload_sign(self) -> None:
        url = f"{self.BASE}/lv/v1/upload_sign"
        sign, dt = self._sign("/lv/v1/upload_sign")
        resp = requests.post(
            url, data=json.dumps({"biz": "pc-recognition"}), headers=self._headers(dt, sign),
            timeout=self.timeout,
        )
        _raise_for_status(resp, "asrtools", "upload_sign")
        data = resp.json().get("data") or {}
        self.access_key = data.get("access_key_id")
        self.secret_key = data.get("secret_access_key")
        self.session_token = data.get("session_token")
        if not (self.access_key and self.secret_key):
            raise AsrError("upload_sign 未返回凭证", reason=REASON_INVALID_RESPONSE, engine="asrtools")

    def _upload_auth(self, file_size: int) -> None:
        request_parameters = (
            "Action=ApplyUploadInner&FileSize=%d&FileType=object&IsInner=1&"
            "SpaceName=lv-mac-recognition&Version=2020-11-19&s=5y0udbjapi" % file_size
        )
        t = datetime.datetime.utcnow()
        amz_date = t.strftime("%Y%m%dT%H%M%SZ")
        datestamp = t.strftime("%Y%m%d")
        headers = {"x-amz-date": amz_date, "x-amz-security-token": self.session_token}
        signature = _aws_signature(self.secret_key, request_parameters, headers, region="cn", service="vod")
        headers["authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key}/{datestamp}/cn/vod/aws4_request, "
            f"SignedHeaders=x-amz-date;x-amz-security-token, Signature={signature}"
        )
        resp = requests.get(
            f"https://vod.bytedanceapi.com/?{request_parameters}", headers=headers, timeout=self.timeout
        )
        _raise_for_status(resp, "asrtools", "upload_auth")
        try:
            info = resp.json()["Result"]["UploadAddress"]
            store = info["StoreInfos"][0]
        except (ValueError, KeyError, IndexError) as e:
            raise AsrError("upload_auth 响应结构异常", reason=REASON_INVALID_RESPONSE, engine="asrtools") from e
        self.store_uri = store["StoreUri"]
        self.auth = store["Auth"]
        self.upload_id = store["UploadID"]
        self.session_key = info.get("SessionKey")
        self.upload_hosts = info["UploadHosts"][0]

    def _upload_file(self, binary: bytes, crc32_hex: str) -> None:
        url = f"https://{self.upload_hosts}/{self.store_uri}?partNumber=1&uploadID={self.upload_id}"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Authorization": self.auth,
            "Content-CRC32": crc32_hex,
        }
        resp = requests.put(url, data=binary, headers=headers, timeout=self.timeout)
        _raise_for_status(resp, "asrtools", "upload_file")
        try:
            if resp.json().get("success") != 0:
                raise AsrError("upload_file 上传失败", reason=REASON_INVALID_RESPONSE, engine="asrtools")
        except ValueError as e:
            raise AsrError("upload_file 响应非 JSON", reason=REASON_INVALID_RESPONSE, engine="asrtools") from e

    def _upload_commit(self, binary: bytes) -> str:
        url = (
            f"https://{self.upload_hosts}/{self.store_uri}"
            f"?uploadID={self.upload_id}&partNumber=1&x-amz-security-token={self.session_token}"
        )
        headers = {"User-Agent": "Mozilla/5.0", "Authorization": self.auth}
        requests.put(url, data=binary, headers=headers, timeout=self.timeout)
        return self.store_uri

    def upload(self, binary: bytes, crc32_hex: str) -> str:
        self._upload_sign()
        self._upload_auth(len(binary))
        self._upload_file(binary, crc32_hex)
        return self._upload_commit(binary)

    # ---- 提交 / 查询 ---- #
    def submit(self, store_uri: str, start_time: float = 0, end_time: float = 6000) -> str:
        url = f"{self.BASE}/lv/v1/audio_subtitle/submit"
        payload = {
            "adjust_endtime": 200,
            "audio": store_uri,
            "caption_type": 2,
            "client_request_id": str(uuid.uuid4()),
            "max_lines": 1,
            "songs_info": [{"end_time": end_time, "id": "", "start_time": start_time}],
            "words_per_line": 16,
        }
        sign, dt = self._sign("/lv/v1/audio_subtitle/submit")
        resp = requests.post(url, json=payload, headers=self._headers(dt, sign), timeout=self.timeout)
        _raise_for_status(resp, "asrtools", "submit")
        try:
            return resp.json()["data"]["id"]
        except (ValueError, KeyError) as e:
            raise AsrError("submit 响应结构异常", reason=REASON_INVALID_RESPONSE, engine="asrtools") from e

    def query(self, query_id: str) -> dict:
        url = f"{self.BASE}/lv/v1/audio_subtitle/query"
        payload = {"id": query_id, "pack_options": {"need_attribute": True}}
        sign, dt = self._sign("/lv/v1/audio_subtitle/query")
        resp = requests.post(url, json=payload, headers=self._headers(dt, sign), timeout=self.timeout)
        _raise_for_status(resp, "asrtools", "query")
        try:
            return resp.json()
        except ValueError as e:
            raise AsrError("query 响应非 JSON", reason=REASON_INVALID_RESPONSE, engine="asrtools") from e


# ============================== 必剪（Bcut） ============================== #


class _BcutClient:
    """B 站必剪 rubick 字幕接口客户端（无需外部签名服务）。"""

    BASE = "https://member.bilibili.com/x/bcut/rubick-interface"
    HEADERS = {
        "User-Agent": "Bilibili/1.0.0 (https://www.bilibili.com)",
        "Content-Type": "application/json",
    }

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout
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
            resp = requests.post(url, data=json.dumps(payload), headers=self.HEADERS, timeout=self.timeout)
        except requests.exceptions.Timeout as e:
            raise AsrError(f"{path} 超时", reason=REASON_TIMEOUT, engine="asrtools") from e
        except requests.exceptions.RequestException as e:
            raise AsrError(f"{path} 网络错误：{e}", reason=REASON_NETWORK, engine="asrtools") from e
        _raise_for_status(resp, "asrtools", path)
        try:
            return resp.json()
        except ValueError as e:
            raise AsrError(f"{path} 响应非 JSON", reason=REASON_INVALID_RESPONSE, engine="asrtools") from e

    def upload(self, binary: bytes) -> None:
        data = self._post(
            "/resource/create",
            {
                "type": 2, "name": "audio.mp3", "size": len(binary),
                "ResourceFileType": "mp3", "model_id": "8",
            },
        ).get("data") or {}
        self._in_boss_key = data.get("in_boss_key")
        self._resource_id = data.get("resource_id")
        self._upload_id = data.get("upload_id")
        self._upload_urls = data.get("upload_urls") or []
        self._per_size = data.get("per_size") or len(binary)
        if not (self._in_boss_key and self._upload_urls):
            raise AsrError("必剪申请上传响应异常", reason=REASON_INVALID_RESPONSE, engine="asrtools")
        clips = len(self._upload_urls)
        etags: list[str] = []
        for clip in range(clips):
            start = clip * self._per_size
            end = (clip + 1) * self._per_size
            try:
                resp = requests.put(
                    self._upload_urls[clip],
                    data=binary[start:end], headers=self.HEADERS, timeout=self.timeout,
                )
            except requests.exceptions.Timeout as e:
                raise AsrError("必剪分片上传超时", reason=REASON_TIMEOUT, engine="asrtools") from e
            except requests.exceptions.RequestException as e:
                raise AsrError(f"必剪分片上传网络错误：{e}", reason=REASON_NETWORK, engine="asrtools") from e
            _raise_for_status(resp, "asrtools", "必剪分片上传")
            etags.append(resp.headers.get("Etag", ""))
        commit = self._post(
            "/resource/create/complete",
            {
                "InBossKey": self._in_boss_key, "ResourceId": self._resource_id,
                "Etags": ",".join(etags), "UploadId": self._upload_id, "model_id": "8",
            },
        ).get("data") or {}
        self._download_url = commit.get("download_url")
        if not self._download_url:
            raise AsrError("必剪提交上传响应异常", reason=REASON_INVALID_RESPONSE, engine="asrtools")

    def create_task(self) -> str:
        data = self._post("/task", {"resource": self._download_url, "model_id": "8"}).get("data") or {}
        self.task_id = data.get("task_id")
        if not self.task_id:
            raise AsrError("必剪创建任务响应异常", reason=REASON_INVALID_RESPONSE, engine="asrtools")
        return self.task_id

    def result(self, task_id: Optional[str] = None) -> dict:
        url = f"{self.BASE}/task/result"
        try:
            resp = requests.get(
                url, params={"model_id": 7, "task_id": task_id or self.task_id},
                headers=self.HEADERS, timeout=self.timeout,
            )
        except requests.exceptions.Timeout as e:
            raise AsrError("必剪查询结果超时", reason=REASON_TIMEOUT, engine="asrtools") from e
        except requests.exceptions.RequestException as e:
            raise AsrError(f"必剪查询结果网络错误：{e}", reason=REASON_NETWORK, engine="asrtools") from e
        _raise_for_status(resp, "asrtools", "必剪查询结果")
        try:
            return resp.json()["data"]
        except (ValueError, KeyError) as e:
            raise AsrError("必剪查询结果响应异常", reason=REASON_INVALID_RESPONSE, engine="asrtools") from e


# ============================== 引擎封装 ============================== #


class AsrToolsEngine(AsrEngine):
    """在线 AsrTools 引擎（剪映 / 必剪），默认首选（design D2）。

    Args:
        provider: ``"jianying"``（默认）/ ``"bcut"``。
        sign_endpoint: 剪映签名服务地址（仅 jianying 使用，MUST 可配置）。
        timeout: 单次 HTTP 请求超时（秒）。
        query_interval / query_max_wait: 必剪轮询间隔与最长等待（秒）。
    """

    name = "asrtools"

    def __init__(
        self,
        provider: str = "jianying",
        sign_endpoint: str = "https://asrtools-update.bkfeng.top/sign",
        timeout: float = 120.0,
        query_interval: float = 2.0,
        query_max_wait: float = 600.0,
    ) -> None:
        self.provider = (provider or "jianying").lower()
        self.sign_endpoint = sign_endpoint
        self.timeout = timeout
        self.query_interval = query_interval
        self.query_max_wait = query_max_wait

    def transcribe(
        self, audio_path: str, on_progress: Optional[ProgressCallback] = None
    ) -> list[Cue]:
        ext = _ext(audio_path)
        if ext not in _SUPPORTED_FORMATS:
            raise AsrError(
                f"不支持的音频格式：{ext or '(无后缀)'}，仅支持 {sorted(_SUPPORTED_FORMATS)}",
                reason=REASON_UNSUPPORTED_FORMAT, engine=self.name,
            )
        if not os.path.exists(audio_path):
            raise AsrError(f"音频文件不存在：{audio_path}", reason=REASON_INVALID_RESPONSE, engine=self.name)

        with open(audio_path, "rb") as f:
            binary = f.read()
        import zlib
        crc32_hex = format(zlib.crc32(binary) & 0xFFFFFFFF, "08x")

        if self.provider == "bcut":
            return self._run_bcut(binary, on_progress)
        return self._run_jianying(binary, crc32_hex, on_progress)

    # ---- 剪映 ---- #
    def _run_jianying(self, binary: bytes, crc32_hex: str, on_progress: Optional[ProgressCallback]) -> list[Cue]:
        client = _JianYingClient(self.sign_endpoint, self.timeout)
        if on_progress:
            on_progress(15, "上传音频（剪映）")
        client.upload(binary, crc32_hex)
        if on_progress:
            on_progress(55, "提交转写任务（剪映）")
        query_id = client.submit(client.store_uri)
        if on_progress:
            on_progress(70, "获取转写结果（剪映）")
        resp = client.query(query_id)
        return self._parse_jianying(resp)

    @staticmethod
    def _parse_jianying(resp: dict) -> list[Cue]:
        try:
            utterances = resp["data"]["utterances"]
        except (KeyError, TypeError) as e:
            raise AsrError("剪映结果缺少 utterances", reason=REASON_INVALID_RESPONSE, engine="asrtools") from e
        cues: list[Cue] = []
        for u in utterances:
            text = (u.get("text") or "").strip()
            if not text:
                continue
            cues.append(Cue(start=_ms(u.get("start_time")), end=_ms(u.get("end_time")), text=text))
        if not cues:
            _LOGGER.info("剪映转写无语音内容，返回空 Cue 列表（不伪造）")
        return cues

    # ---- 必剪 ---- #
    def _run_bcut(self, binary: bytes, on_progress: Optional[ProgressCallback]) -> list[Cue]:
        client = _BcutClient(self.timeout)
        if on_progress:
            on_progress(15, "上传音频（必剪）")
        client.upload(binary)
        if on_progress:
            on_progress(50, "提交转写任务（必剪）")
        client.create_task()
        if on_progress:
            on_progress(65, "获取转写结果（必剪）")
        # 轮询（state==4 表示完成）
        deadline = time.time() + self.query_max_wait
        task_resp: dict = {}
        while True:
            task_resp = client.result()
            state = task_resp.get("state")
            if state == 4:
                break
            if time.time() > deadline:
                raise AsrError("必剪转写轮询超时", reason=REASON_TIMEOUT, engine=self.name)
            time.sleep(self.query_interval)
        return self._parse_bcut(task_resp)

    @staticmethod
    def _parse_bcut(task_resp: dict) -> list[Cue]:
        result_raw = task_resp.get("result")
        if isinstance(result_raw, str):
            try:
                result_raw = json.loads(result_raw)
            except ValueError as e:
                raise AsrError("必剪结果 JSON 解析失败", reason=REASON_INVALID_RESPONSE, engine="asrtools") from e
        if not isinstance(result_raw, dict):
            raise AsrError("必剪结果结构异常", reason=REASON_INVALID_RESPONSE, engine="asrtools")
        utterances = result_raw.get("utterances") or []
        cues: list[Cue] = []
        for u in utterances:
            text = (u.get("transcript") or u.get("text") or "").strip()
            if not text:
                continue
            cues.append(Cue(start=_ms(u.get("start_time")), end=_ms(u.get("end_time")), text=text))
        if not cues:
            _LOGGER.info("必剪转写无语音内容，返回空 Cue 列表（不伪造）")
        return cues


def _ms(value) -> float:
    """毫秒数值 → 秒（float）；非法值返回 0.0。"""
    try:
        return float(value) / 1000.0
    except (TypeError, ValueError):
        return 0.0
