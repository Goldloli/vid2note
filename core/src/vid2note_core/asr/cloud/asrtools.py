"""AsrTools b 接口云端 ASR 适配器

流程（设计稿第六节）：
  1. 若音频超过阈值（默认 60s），用 ffmpeg 切分成等长块
  2. 每块上传到云端 ASR 接口
  3. 轮询每块的识别结果（异步任务）
  4. 合并各块时间戳（块偏移 + 块内时间戳）→ 单个 ASRResult

b 接口是"非官方"接口，结构随时可能变（风险见设计稿）。应对：
  - 所有 HTTP 调用细节集中在适配器内，外部通过 httpx.AsyncClient 注入
  - 响应结构不匹配时抛 ASRToolBChanged（明确错误码）
  - 网络失败抛 ASRNetworkError（可重试）

真实 base_url / 端点需调研后通过构造参数或环境变量 ASRTOOLS_BASE_URL 注入；
默认值仅用于测试与占位。接口契约在 _parse_* 方法中集中描述，便于适配变更。
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx
from vid2note_core.asr.base import IASR, ASRResult, ASRSegment
from vid2note_core.errors import ASRNetworkError, ASRToolBChanged


class AsrToolsBLLM(IASR):
    """AsrTools b 接口云端 ASR。

    通过 httpx.AsyncClient 与云端交互。client 可注入（测试用 respx/mock）。
    """

    name = "asrtools-b"
    is_cloud = True
    requires_local_gpu = False

    # b 接口端点（占位；真实值经环境变量 ASRTOOLS_BASE_URL 或构造参数注入）
    BASE_URL = "https://api.example-asr.com/v1"
    CHUNK_SEC = 60
    POLL_INTERVAL = 1.0
    POLL_TIMEOUT = 300.0  # 单块最大轮询时长（秒）

    def __init__(
        self,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        chunk_sec: int | None = None,
        poll_interval: float | None = None,
        poll_timeout: float | None = None,
        api_key: str | None = None,
        ffmpeg_path: str | None = None,
    ):
        self.base_url = (base_url or os.environ.get("ASRTOOLS_BASE_URL") or self.BASE_URL).rstrip(
            "/"
        )
        self.client = client  # 懒加载：为 None 时在首次调用时创建
        self.api_key = api_key or os.environ.get("ASRTOOLS_API_KEY")
        self.chunk_sec = chunk_sec or self.CHUNK_SEC
        self.poll_interval = poll_interval if poll_interval is not None else self.POLL_INTERVAL
        self.poll_timeout = poll_timeout if poll_timeout is not None else self.POLL_TIMEOUT
        self.ffmpeg_path = ffmpeg_path or os.environ.get("VID2NOTE_FFMPEG_PATH") or "ffmpeg"

    # ── 主流程 ─────────────────────────────────────────────

    async def transcribe(self, audio_path: Path, opts: dict) -> ASRResult:  # type: ignore[override]
        language = opts.get("language", "zh")
        client = self._get_client()
        try:
            chunks = await asyncio.to_thread(self._chunk_audio, audio_path)
            results = await self._transcribe_chunks(client, chunks, language)
        except (ASRNetworkError, ASRToolBChanged):
            raise
        except httpx.HTTPError as e:
            raise ASRNetworkError(str(e)) from e
        finally:
            # 只关闭自建的 client，注入的 client 由调用方管理
            if self.client is None and client is not None:
                await client.aclose()

        return self._merge_results(results, language)

    def is_available(self) -> bool:
        return True  # 云端始终可用（网络允许时）

    # ── 分块 ───────────────────────────────────────────────

    def _chunk_audio(self, audio_path: Path) -> list[Path]:
        """用 ffmpeg 把音频切成 chunk_sec 秒的块。短于阈值的音频直接返回原文件。

        返回各块文件路径列表。若 ffmpeg 不可用或探测时长失败，退化为整段处理。
        """
        duration = self._probe_duration(audio_path)
        if duration <= 0 or duration <= self.chunk_sec:
            return [audio_path]

        out_dir = Path(tempfile.mkdtemp(prefix="vid2note_asr_"))
        chunks: list[Path] = []
        num_chunks = int(duration // self.chunk_sec) + (1 if duration % self.chunk_sec else 0)
        for i in range(num_chunks):
            start = i * self.chunk_sec
            out_file = out_dir / f"chunk_{i:04d}.wav"
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-ss",
                str(start),
                "-t",
                str(self.chunk_sec),
                "-i",
                str(audio_path),
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                str(out_file),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0 or not out_file.exists():
                # 切块失败：退化为整段处理
                for c in chunks:
                    c.unlink(missing_ok=True)
                return [audio_path]
            chunks.append(out_file)
        return chunks or [audio_path]

    def _probe_duration(self, audio_path: Path) -> float:
        """用 ffprobe 探测时长（秒）。失败返回 0。"""
        try:
            probe = subprocess.run(
                [
                    self.ffmpeg_path.replace("ffmpeg", "ffprobe"),
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(audio_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return float(probe.stdout.strip()) if probe.returncode == 0 else 0.0
        except Exception:  # noqa: BLE001 - 探测失败按整段处理
            return 0.0

    # ── 上传 + 轮询 ────────────────────────────────────────

    async def _transcribe_chunks(
        self, client: httpx.AsyncClient, chunks: list[Path], language: str
    ) -> list[list[ASRSegment]]:
        """并发上传各块并轮询结果，返回每块的段列表（块内相对时间戳）。"""
        tasks = [
            self._process_one_chunk(client, chunk, i, language) for i, chunk in enumerate(chunks)
        ]
        return await asyncio.gather(*tasks)

    async def _process_one_chunk(
        self, client: httpx.AsyncClient, chunk_path: Path, index: int, language: str
    ) -> list[ASRSegment]:
        """上传单块 → 轮询 → 解析块内时间戳。"""
        task_id = await self._upload_chunk(client, chunk_path, language)
        result = await self._poll_result(client, task_id)
        return self._parse_chunk_segments(result, index)

    async def _upload_chunk(
        self, client: httpx.AsyncClient, chunk_path: Path, language: str
    ) -> str:
        """上传音频块，返回云端任务 id。

        契约：POST {base_url}/asr/upload，multipart 表单 file + language，
        响应 JSON 必须含 {"task_id": "..."}。
        """
        headers = self._auth_headers()
        with open(chunk_path, "rb") as f:
            files = {"file": (chunk_path.name, f, "audio/wav")}
            data = {"language": language}
            try:
                resp = await client.post(
                    f"{self.base_url}/asr/upload", files=files, data=data, headers=headers
                )
            except httpx.HTTPError as e:
                raise ASRNetworkError(str(e)) from e

        self._check_http_ok(resp, context="upload")
        payload = self._safe_json(resp, context="upload")
        task_id = payload.get("task_id")
        if not task_id:
            raise ASRToolBChanged(f"upload 响应缺少 task_id 字段: {payload}")
        return str(task_id)

    async def _poll_result(self, client: httpx.AsyncClient, task_id: str) -> dict:
        """轮询单块结果直到完成。

        契约：GET {base_url}/asr/result/{task_id}，
        响应 JSON 含 {"status": "processing"|"done"|"failed", "result": {...}}。
        """
        headers = self._auth_headers()
        deadline = asyncio.get_event_loop().time() + self.poll_timeout
        while True:
            try:
                resp = await client.get(f"{self.base_url}/asr/result/{task_id}", headers=headers)
            except httpx.HTTPError as e:
                raise ASRNetworkError(str(e)) from e

            self._check_http_ok(resp, context="poll")
            payload = self._safe_json(resp, context="poll")

            if "status" not in payload:
                raise ASRToolBChanged(f"poll 响应缺少 status 字段: {payload}")
            status = payload["status"]
            if status == "done":
                return payload.get("result") or {}
            if status == "failed":
                raise ASRNetworkError(f"云端识别失败 task={task_id}: {payload.get('error', '')}")
            if asyncio.get_event_loop().time() > deadline:
                raise ASRNetworkError(f"轮询超时 task={task_id}")

            await asyncio.sleep(self.poll_interval)

    # ── 响应解析 ───────────────────────────────────────────

    def _parse_chunk_segments(self, result: dict, chunk_index: int) -> list[ASRSegment]:
        """解析单块结果为段列表（块内相对时间戳，单位毫秒）。

        支持两种常见结构（b 接口可能返回任一）：
          A. {"sentences": [{"text": "...", "begin"/"start": ms, "end": ms}]}
          B. {"text": "全文", "timestamps": [[start_ms, end_ms, text], ...]}

        结构完全无法识别时抛 ASRToolBChanged。
        """
        segments: list[ASRSegment] = []

        # 结构 A：sentences 数组
        sentences = result.get("sentences") or result.get("segments")
        if isinstance(sentences, list):
            for s in sentences:
                if not isinstance(s, dict):
                    continue
                text = s.get("text", "")
                start = self._to_ms(s.get("begin", s.get("start", s.get("start_ms", 0))))
                end = self._to_ms(s.get("end", s.get("end_ms", start)))
                if text:
                    segments.append(ASRSegment(start_ms=start, end_ms=end, text=text))
            if segments:
                return segments

        # 结构 B：timestamps 数组 [start, end, text]
        timestamps = result.get("timestamps")
        if isinstance(timestamps, list) and timestamps:
            for t in timestamps:
                if isinstance(t, (list, tuple)) and len(t) >= 3:
                    start = self._to_ms(t[0])
                    end = self._to_ms(t[1])
                    text = str(t[2])
                    if text:
                        segments.append(ASRSegment(start_ms=start, end_ms=end, text=text))
            if segments:
                return segments

        # 仅含纯文本（无时间戳）：作为单段
        text_only = result.get("text")
        if isinstance(text_only, str) and text_only.strip():
            return [ASRSegment(start_ms=0, end_ms=0, text=text_only.strip())]

        # 完全无法识别
        raise ASRToolBChanged(f"无法识别的块结果结构 (chunk {chunk_index}): {result}")

    def _merge_results(self, chunk_results: list[list[ASRSegment]], language: str) -> ASRResult:
        """合并各块段列表：加上块时间偏移，拼接全文。"""
        all_segments: list[ASRSegment] = []
        texts: list[str] = []
        for i, segs in enumerate(chunk_results):
            offset_ms = i * self.chunk_sec * 1000
            for seg in segs:
                all_segments.append(
                    ASRSegment(
                        start_ms=seg.start_ms + offset_ms,
                        end_ms=seg.end_ms + offset_ms if seg.end_ms else seg.end_ms,
                        text=seg.text,
                    )
                )
                if seg.text:
                    texts.append(seg.text)
        duration_ms = all_segments[-1].end_ms if all_segments else 0
        full = "".join(texts) if language == "zh" else " ".join(texts)
        return ASRResult(
            text_full=full,
            segments=all_segments,
            language=language,
            duration_ms=duration_ms,
        )

    # ── HTTP 辅助 ──────────────────────────────────────────

    def _get_client(self) -> httpx.AsyncClient:
        if self.client is not None:
            return self.client
        return httpx.AsyncClient(timeout=30.0)

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def _check_http_ok(self, resp: httpx.Response, context: str) -> None:
        if resp.status_code >= 500:
            raise ASRNetworkError(f"{context} 服务端错误 {resp.status_code}")
        if resp.status_code >= 400:
            raise ASRNetworkError(f"{context} 请求错误 {resp.status_code}: {resp.text[:200]}")

    def _safe_json(self, resp: httpx.Response, context: str) -> dict:
        try:
            data = resp.json()
        except Exception as e:  # noqa: BLE001 - 非 JSON 响应视为接口变更
            raise ASRToolBChanged(f"{context} 响应非 JSON: {resp.text[:200]}") from e
        if not isinstance(data, dict):
            raise ASRToolBChanged(f"{context} 响应不是对象: {data!r}")
        return data

    @staticmethod
    def _to_ms(value: Any) -> int:
        """把秒或毫秒统一为毫秒整数。<=100 的视为秒（毫秒数太小无意义）。"""
        try:
            v = float(value)
        except (TypeError, ValueError):
            return 0
        if v <= 100:
            return int(v * 1000)  # 视为秒
        return int(v)
