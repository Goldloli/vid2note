"""AsrTools b 接口云端 ASR 适配器测试

用 respx mock HTTP（upload + poll），mock ffmpeg/ffprobe 子进程，
覆盖：单块识别、分块合并、响应结构变更检测、网络错误、超长音频分块、纯文本回退。
"""

from unittest.mock import patch

import httpx
import pytest
import respx
from vid2note_core.asr.cloud.asrtools import AsrToolsBLLM
from vid2note_core.errors import ASRNetworkError, ASRToolBChanged

BASE = "https://api.example-asr.com/v1"


@pytest.fixture
def short_audio(tmp_path):
    """短音频文件（内容无所谓，分块逻辑被 mock 掉）"""
    p = tmp_path / "audio.wav"
    p.write_bytes(b"RIFF...fake wav")
    return p


def _patch_ffmpeg_no_chunk():
    """mock 探测时长返回 30s（< chunk_sec），跳过实际分块。"""
    return patch.object(AsrToolsBLLM, "_probe_duration", return_value=30.0)


def _patch_ffmpeg_chunked(durations):
    """mock 探测时长返回超长，并 mock 分块返回 N 个假块文件。"""
    n = len(durations)

    def _fake_chunk(self, audio_path):
        # 返回 n 个已存在的假块文件
        return [audio_path for _ in range(n)]

    return (
        patch.object(AsrToolsBLLM, "_probe_duration", return_value=180.0),
        patch.object(AsrToolsBLLM, "_chunk_audio", _fake_chunk),
    )


@pytest.mark.asyncio
async def test_transcribe_single_chunk_success(short_audio):
    """单块：upload → poll(done) → 解析 sentences 结构"""
    with _patch_ffmpeg_no_chunk(), respx.mock(base_url=BASE) as mock:
        mock.post("/asr/upload").mock(return_value=httpx.Response(200, json={"task_id": "t1"}))
        mock.get("/asr/result/t1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "done",
                    "result": {
                        "sentences": [
                            {"text": "你好", "begin": 0, "end": 1500},
                            {"text": "世界", "begin": 1500, "end": 3000},
                        ]
                    },
                },
            )
        )
        asr = AsrToolsBLLM(base_url=BASE, poll_interval=0.01, poll_timeout=5)
        result = await asr.transcribe(short_audio, {"language": "zh"})

    assert result.language == "zh"
    assert result.text_full == "你好世界"
    assert len(result.segments) == 2
    assert result.segments[0].start_ms == 0
    assert result.segments[1].start_ms == 1500


@pytest.mark.asyncio
async def test_transcribe_polling_until_done(short_audio):
    """轮询：首次 processing，第二次 done"""
    responses = [
        httpx.Response(200, json={"status": "processing"}),
        httpx.Response(200, json={"status": "done", "result": {"text": "完成"}}),
    ]
    with _patch_ffmpeg_no_chunk(), respx.mock(base_url=BASE) as mock:
        mock.post("/asr/upload").mock(return_value=httpx.Response(200, json={"task_id": "t1"}))
        mock.get("/asr/result/t1").mock(side_effect=responses)
        asr = AsrToolsBLLM(base_url=BASE, poll_interval=0.01, poll_timeout=5)
        result = await asr.transcribe(short_audio, {"language": "zh"})

    assert result.text_full == "完成"
    assert len(result.segments) == 1
    assert result.segments[0].text == "完成"


@pytest.mark.asyncio
async def test_transcribe_multi_chunk_merge_timestamps(short_audio):
    """分块：2 块各自识别，时间戳按块偏移合并"""
    p1, p2 = _patch_ffmpeg_chunked([30, 30])
    with p1, p2, respx.mock(base_url=BASE) as mock:
        # 两块各上传，返回不同 task_id
        upload_route = mock.post("/asr/upload")
        upload_route.mock(
            side_effect=[
                httpx.Response(200, json={"task_id": "t1"}),
                httpx.Response(200, json={"task_id": "t2"}),
            ]
        )
        mock.get("/asr/result/t1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "done",
                    "result": {"sentences": [{"text": "块1", "begin": 0, "end": 1000}]},
                },
            )
        )
        mock.get("/asr/result/t2").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "done",
                    "result": {"sentences": [{"text": "块2", "begin": 0, "end": 1000}]},
                },
            )
        )
        asr = AsrToolsBLLM(base_url=BASE, chunk_sec=60, poll_interval=0.01, poll_timeout=5)
        result = await asr.transcribe(short_audio, {"language": "zh"})

    # 块1 偏移 0，块2 偏移 60s=60000ms
    assert result.text_full == "块1块2"
    assert result.segments[0].start_ms == 0
    assert result.segments[1].start_ms == 60000  # 第二块加上 60s 偏移
    assert upload_route.call_count == 2


@pytest.mark.asyncio
async def test_transcribe_timestamps_structure(short_audio):
    """支持 timestamps 数组结构 [start, end, text]"""
    with _patch_ffmpeg_no_chunk(), respx.mock(base_url=BASE) as mock:
        mock.post("/asr/upload").mock(return_value=httpx.Response(200, json={"task_id": "t1"}))
        mock.get("/asr/result/t1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "done",
                    "result": {"timestamps": [[0, 1000, "A"], [1000, 2000, "B"]]},
                },
            )
        )
        asr = AsrToolsBLLM(base_url=BASE, poll_interval=0.01, poll_timeout=5)
        result = await asr.transcribe(short_audio, {"language": "en"})

    assert result.text_full == "A B"  # 英文用空格连接
    assert result.segments[0].text == "A"
    assert result.segments[1].start_ms == 1000


@pytest.mark.asyncio
async def test_transcribe_schema_change_missing_task_id(short_audio):
    """upload 响应缺少 task_id → ASRToolBChanged"""
    with _patch_ffmpeg_no_chunk(), respx.mock(base_url=BASE) as mock:
        mock.post("/asr/upload").mock(return_value=httpx.Response(200, json={"oops": "no id"}))
        asr = AsrToolsBLLM(base_url=BASE)
        with pytest.raises(ASRToolBChanged):
            await asr.transcribe(short_audio, {})


@pytest.mark.asyncio
async def test_transcribe_schema_change_unrecognized_result(short_audio):
    """块结果结构完全无法识别 → ASRToolBChanged"""
    with _patch_ffmpeg_no_chunk(), respx.mock(base_url=BASE) as mock:
        mock.post("/asr/upload").mock(return_value=httpx.Response(200, json={"task_id": "t1"}))
        mock.get("/asr/result/t1").mock(
            return_value=httpx.Response(
                200, json={"status": "done", "result": {"weird_field": 123}}
            )
        )
        asr = AsrToolsBLLM(base_url=BASE, poll_interval=0.01, poll_timeout=5)
        with pytest.raises(ASRToolBChanged):
            await asr.transcribe(short_audio, {})


@pytest.mark.asyncio
async def test_transcribe_network_error_upload(short_audio):
    """上传网络错误 → ASRNetworkError"""
    with _patch_ffmpeg_no_chunk(), respx.mock(base_url=BASE) as mock:
        mock.post("/asr/upload").mock(side_effect=httpx.ConnectError("refused"))
        asr = AsrToolsBLLM(base_url=BASE)
        with pytest.raises(ASRNetworkError):
            await asr.transcribe(short_audio, {})


@pytest.mark.asyncio
async def test_transcribe_cloud_failed_status(short_audio):
    """云端返回 failed 状态 → ASRNetworkError"""
    with _patch_ffmpeg_no_chunk(), respx.mock(base_url=BASE) as mock:
        mock.post("/asr/upload").mock(return_value=httpx.Response(200, json={"task_id": "t1"}))
        mock.get("/asr/result/t1").mock(
            return_value=httpx.Response(200, json={"status": "failed", "error": "audio corrupt"})
        )
        asr = AsrToolsBLLM(base_url=BASE, poll_interval=0.01, poll_timeout=5)
        with pytest.raises(ASRNetworkError):
            await asr.transcribe(short_audio, {})


@pytest.mark.asyncio
async def test_transcribe_http_500(short_audio):
    """服务端 5xx → ASRNetworkError"""
    with _patch_ffmpeg_no_chunk(), respx.mock(base_url=BASE) as mock:
        mock.post("/asr/upload").mock(return_value=httpx.Response(503, text="unavailable"))
        asr = AsrToolsBLLM(base_url=BASE)
        with pytest.raises(ASRNetworkError):
            await asr.transcribe(short_audio, {})


@pytest.mark.asyncio
async def test_transcribe_non_json_response(short_audio):
    """响应非 JSON → ASRToolBChanged"""
    with _patch_ffmpeg_no_chunk(), respx.mock(base_url=BASE) as mock:
        mock.post("/asr/upload").mock(return_value=httpx.Response(200, text="<html>error</html>"))
        asr = AsrToolsBLLM(base_url=BASE)
        with pytest.raises(ASRToolBChanged):
            await asr.transcribe(short_audio, {})


@pytest.mark.asyncio
async def test_transcribe_text_only_fallback(short_audio):
    """结果仅含 text 无时间戳 → 退化为单段"""
    with _patch_ffmpeg_no_chunk(), respx.mock(base_url=BASE) as mock:
        mock.post("/asr/upload").mock(return_value=httpx.Response(200, json={"task_id": "t1"}))
        mock.get("/asr/result/t1").mock(
            return_value=httpx.Response(
                200, json={"status": "done", "result": {"text": "纯文本无时间"}}
            )
        )
        asr = AsrToolsBLLM(base_url=BASE, poll_interval=0.01, poll_timeout=5)
        result = await asr.transcribe(short_audio, {"language": "zh"})

    assert result.text_full == "纯文本无时间"
    assert len(result.segments) == 1
    assert result.segments[0].start_ms == 0


def test_is_available():
    assert AsrToolsBLLM().is_available() is True


def test_to_ms_seconds_vs_millis():
    """<=100 视为秒，>100 视为毫秒"""
    assert AsrToolsBLLM._to_ms(1.5) == 1500
    assert AsrToolsBLLM._to_ms(1500) == 1500
    assert AsrToolsBLLM._to_ms("not a number") == 0
    assert AsrToolsBLLM._to_ms(None) == 0


def test_base_url_from_env(monkeypatch):
    monkeypatch.setenv("ASRTOOLS_BASE_URL", "https://custom.example.com/v2/")
    asr = AsrToolsBLLM()
    assert asr.base_url == "https://custom.example.com/v2"  # 去掉末尾斜杠
