"""speech_to_text 模块测试（spec speech-to-text / design D2/D3 / CONTRACT §6.2）。

覆盖：
- 输入输出契约（SRT 格式 / 单调 / 缺文件报错 / 静音不伪造）
- 三引擎可经配置实例化、引擎选择策略（online_first / single）
- 在线降级结构化日志 + 全不可用报错
- VAD 时间戳偏移拼回（段@300s 段内 10s → 310s）、短音频不分段
- CONTRACT transcribe(ctx,...) DAG 入口
"""
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from src.speech_to_text import (
    AsrConfig,
    AsrEngine,
    AsrError,
    AudioSegment,
    Cue,
    BcutEngine,
    WhisperCppEngine,
    ExternalAsrEngine,
    build_engines,
    cues_to_srt,
    format_srt_timestamp,
    parse_srt_to_cues,
    resolve_engine_order,
    sanitize_cues,
    transcribe,
    transcribe_to_srt,
)
from src.speech_to_text import pipeline as P


# ----------------------------- fixtures ----------------------------- #


@pytest.fixture(scope="module")
def short_wav(tmp_path_factory):
    """生成 3 秒静音 WAV（短音频，不触发 VAD）。"""
    p = tmp_path_factory.mktemp("asr") / "short.wav"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=16000",
         "-t", "3", str(p)],
        check=True,
    )
    return str(p)


class _StubOnline(AsrEngine):
    name = "bcut"

    def __init__(self, fail=False, reason="rate_limited", status_code=429, cues=None):
        self._fail = fail
        self._reason = reason
        self._status = status_code
        self._cues = cues if cues is not None else [Cue(0.0, 1.0, "在线字幕")]

    def transcribe(self, audio_path, on_progress=None):
        if self._fail:
            raise AsrError("限流", reason=self._reason, engine="bcut", status_code=self._status)
        return list(self._cues)


class _StubLocal(AsrEngine):
    name = "whisper_cpp"

    def __init__(self, cues=None):
        self._cues = cues if cues is not None else [Cue(0.0, 1.0, "本地字幕")]

    def transcribe(self, audio_path, on_progress=None):
        return list(self._cues)


@pytest.fixture
def patch_engines(monkeypatch):
    """注入 stub 引擎，返回一个可改写的 dict。"""
    holder = {}

    def _install(engines_dict):
        holder.clear()
        holder.update(engines_dict)
        monkeypatch.setattr(P, "build_engines", lambda cfg: holder)

    return _install


# ----------------------------- 输入输出契约 ----------------------------- #


class TestCueSrt:
    def test_cues_to_srt_format(self):
        srt = cues_to_srt([Cue(0, 1.5, "你好"), Cue(1.5, 2.5, "世界")])
        assert "1\n00:00:00,000 --> 00:00:01,500\n你好\n" in srt
        assert "2\n00:00:01,500 --> 00:00:02,500\n世界\n" in srt

    def test_empty_cuces_not_faked(self):
        # spec：无 ASR 结果段不伪造字幕条目
        assert cues_to_srt([]) == ""

    def test_monotonic_and_no_overlap(self):
        cues = sanitize_cues([Cue(0, 3, "a"), Cue(2.5, 4, "重叠"), Cue(5, 6, "b")])
        assert all(cues[i].end <= cues[i + 1].start for i in range(len(cues) - 1))
        assert all(cues[i].start <= cues[i + 1].start for i in range(len(cues) - 1))

    def test_drop_empty_and_invalid(self):
        cues = sanitize_cues([Cue(0, 1, ""), Cue(5, 3, "倒序"), Cue(2, 4, "ok")])
        assert [c.text for c in cues] == ["ok"]

    def test_timestamp_format_310(self):
        # spec：段从 300s 起、段内 10s → 00:05:10
        assert format_srt_timestamp(310.0) == "00:05:10,000"

    def test_parse_srt_strips_html(self):
        cues = parse_srt_to_cues("1\n00:00:01,000 --> 00:00:02,000\nhello <i>world</i>\n")
        assert cues[0].text == "hello world"

    def test_missing_audio_raises_no_empty_srt(self, tmp_path):
        with pytest.raises(AsrError):
            transcribe_to_srt(str(tmp_path / "nope.wav"), AsrConfig())


# ----------------------------- 引擎与策略 ----------------------------- #


class TestEngineConfig:
    def test_build_three_engines(self):
        engines = build_engines(AsrConfig(external_endpoint="http://x"))
        assert isinstance(engines["bcut"], BcutEngine)
        assert isinstance(engines["whisper_cpp"], WhisperCppEngine)
        assert isinstance(engines["external"], ExternalAsrEngine)

    def test_resolve_online_first_order(self):
        order = resolve_engine_order(AsrConfig(strategy="online_first", engine="bcut"))
        assert order[0] == "bcut"
        assert order[-1] == "whisper_cpp"  # 本地兜底

    def test_resolve_single_no_fallback(self):
        order = resolve_engine_order(AsrConfig(strategy="single", engine="bcut"))
        assert order == ["bcut"]

    def test_resolve_external_online_first(self):
        order = resolve_engine_order(AsrConfig(strategy="online_first", engine="external"))
        assert order[0] == "external" and "whisper_cpp" in order

    def test_from_settings_parses_json_blob(self):
        cfg = AsrConfig.from_settings({
            "asr.engine": "external",
            "asr.strategy": "single",
            "asr.config": '{"endpoint": "http://my-asr", "whisper_model_path": "/m", "bcut_timeout": 8}',
        })
        assert cfg.engine == "external"
        assert cfg.strategy == "single"
        assert cfg.external_endpoint == "http://my-asr"
        assert cfg.whisper_model_path == "/m"
        assert cfg.bcut_timeout == 8

    def test_bcut_parses_string_result_and_millisecond_timestamps(self):
        cues = BcutEngine._parse_result({
            "result": (
                '{"utterances": ['
                '{"start_time": 1250, "end_time": 2750, "transcript": "测试"}'
                ']}'
            ),
        })
        assert cues == [Cue(start=1.25, end=2.75, text="测试")]

    def test_bcut_does_not_fabricate_empty_transcript(self):
        assert BcutEngine._parse_result({"result": {"utterances": []}}) == []


# ----------------------------- 降级 / 不可用 ----------------------------- #


class TestDegradation:
    def test_online_first_degrades_with_log(self, short_wav, patch_engines):
        logs = []
        patch_engines({"bcut": _StubOnline(fail=True), "whisper_cpp": _StubLocal()})
        srt = transcribe_to_srt(
            short_wav, AsrConfig(strategy="online_first", whisper_model_path="/tmp/x"),
            on_log=lambda lv, line: logs.append((lv, line)),
        )
        assert "本地字幕" in srt
        # 结构化降级事件已写（warn 级别 + 原因）
        joined = " ".join(line for _, line in logs)
        assert "降级" in joined and "bcut" in joined and "whisper_cpp" in joined

    def test_single_does_not_degrade(self, short_wav, patch_engines):
        patch_engines({"bcut": _StubOnline(fail=True), "whisper_cpp": _StubLocal()})
        with pytest.raises(AsrError) as exc:
            transcribe_to_srt(
                short_wav, AsrConfig(strategy="single", engine="bcut", whisper_model_path="/tmp/x"),
            )
        assert exc.value.engine == "bcut"  # 失败于原引擎，未降级

    def test_all_unavailable_raises(self, short_wav, patch_engines):
        patch_engines({"bcut": _StubOnline(fail=True)})
        with pytest.raises(AsrError) as exc:
            transcribe_to_srt(short_wav, AsrConfig(strategy="online_first"))
        assert "无可用" in str(exc.value)


# ----------------------------- VAD 偏移拼回 ----------------------------- #


class TestVadMerge:
    def test_offset_merge_300s_to_310s(self, short_wav):
        # 段内产出 0-2s 与 10-12s 两条；段@300s → 拼回 300/302 与 310/312
        class Eng(AsrEngine):
            name = "whisper_cpp"
            def transcribe(self, audio_path, on_progress=None):
                return [Cue(10.0, 12.0, "段内十秒"), Cue(0.0, 2.0, "段内零秒")]

        segs = [
            AudioSegment(start_offset=0.0, duration=60.0, path=short_wav),
            AudioSegment(start_offset=300.0, duration=60.0, path=short_wav),
        ]
        resolver = P._EngineResolver({"whisper_cpp": Eng()}, ["whisper_cpp"], strategy="single")
        merged = P._transcribe_segments_parallel(segs, resolver, AsrConfig(concurrency=2), None, None, None)
        starts = sorted(c.start for c in merged)
        assert 310.0 in starts and 300.0 in starts  # 偏移叠加正确
        # 单调、无重叠/空洞跨段
        assert all(merged[i].end <= merged[i + 1].start for i in range(len(merged) - 1))


# ----------------------------- 短音频不分段 ----------------------------- #


class TestShortAudio:
    def test_short_audio_no_split(self, short_wav, monkeypatch):
        # 短音频 transcribe_audio 不应调用 split_audio_by_silence
        called = {"split": False}
        monkeypatch.setattr(
            P, "split_audio_by_silence",
            lambda *a, **k: called.__setitem__("split", True) or [AudioSegment(0, 3, short_wav)],
        )
        from src.speech_to_text import transcribe_audio
        monkeypatch.setattr(P, "build_engines",
                            lambda cfg: {"bcut": _StubOnline(), "whisper_cpp": _StubLocal()})
        seen = []
        transcribe_audio(short_wav, AsrConfig(strategy="single", engine="bcut"),
                         on_log=lambda lv, line: seen.append(line))
        assert called["split"] is False
        assert any("整段转录" in ln for ln in seen)


# ----------------------------- CONTRACT DAG 入口 ----------------------------- #


class _FakeCtx:
    def __init__(self, data_root):
        self.data_root = Path(data_root)
        self.registered = []
        self.logs = []
        self.task = type("T", (), {"task_id": "task_t"})()
        self.work_temp = Path(data_root) / "temp" / "task_t"

    class _Cancel:
        def is_cancelled(self):
            return False

    @property
    def cancel(self):
        return _FakeCtx._Cancel()

    def emit_progress(self, p, m):
        pass

    def emit_log(self, lv, line):
        self.logs.append((lv, line))

    def register_product(self, kind, rel, size):
        self.registered.append((kind, rel, size))


class TestContractEntry:
    def test_transcribe_writes_srt_and_registers(self, short_wav, monkeypatch):
        with tempfile.TemporaryDirectory() as td:
            arel = "audio/task_t/test.wav"
            aabs = Path(td) / arel
            aabs.parent.mkdir(parents=True)
            aabs.write_bytes(Path(short_wav).read_bytes())
            monkeypatch.setattr(P, "build_engines",
                                lambda cfg: {"bcut": _StubOnline(), "whisper_cpp": _StubLocal()})
            ctx = _FakeCtx(td)
            srt_rel = "srt/task_t/test.srt"
            ret = transcribe(ctx, arel, srt_rel,
                             AsrConfig(strategy="single", engine="whisper_cpp", whisper_model_path="/tmp/x"))
            assert ret == srt_rel
            assert (Path(td) / srt_rel).exists()
            assert ctx.registered == [("srt", srt_rel, (Path(td) / srt_rel).stat().st_size)]

    def test_transcribe_missing_audio_no_srt(self, tmp_path, monkeypatch):
        monkeypatch.setattr(P, "build_engines",
                            lambda cfg: {"bcut": _StubOnline(), "whisper_cpp": _StubLocal()})
        ctx = _FakeCtx(str(tmp_path))
        srt_rel = "srt/task_t/missing.srt"
        with pytest.raises(AsrError):
            transcribe(ctx, "audio/task_t/nope.wav", srt_rel,
                       AsrConfig(strategy="single", engine="whisper_cpp", whisper_model_path="/tmp/x"))
        assert not (tmp_path / srt_rel).exists()
