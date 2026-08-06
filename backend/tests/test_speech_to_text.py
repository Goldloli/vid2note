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
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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
from src.speech_to_text import bcut_budget as BB
from src.speech_to_text import vad as V


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


@pytest.fixture(autouse=True)
def reset_runtime_coordination(monkeypatch):
    """隔离进程级冷却与本地任务槽，避免并发测试相互污染。"""
    monkeypatch.setattr(BB, "_PROCESS_COOLDOWN_UNTIL", 0.0)
    monkeypatch.setattr(P, "_LOCAL_TASK_SLOT", threading.BoundedSemaphore(1))
    monkeypatch.setattr(P, "_BCUT_PROBE_LOCK", threading.Lock())


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
        assert cfg.online_concurrency == 3
        assert cfg.local_concurrency == 1
        assert cfg.online_target_segment_seconds == 280
        assert cfg.online_audio_format == "mp3"
        assert cfg.cache_dir.endswith("asr_cache")

    def test_from_settings_migrates_legacy_concurrency_and_target(self):
        cfg = AsrConfig.from_settings({
            "asr.config": '{"concurrency":2,"vad_target_segment_seconds":90}',
        })
        assert cfg.online_concurrency == 2
        assert cfg.local_concurrency == 1
        assert cfg.online_target_segment_seconds == 90
        assert cfg.local_target_segment_seconds == 90

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
        self.metadata = []
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

    def register_node_metadata(self, metadata):
        self.metadata.append(dict(metadata))


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
            assert ctx.metadata and ctx.metadata[0]["segment_count"] == 1

    def test_transcribe_missing_audio_no_srt(self, tmp_path, monkeypatch):
        monkeypatch.setattr(P, "build_engines",
                            lambda cfg: {"bcut": _StubOnline(), "whisper_cpp": _StubLocal()})
        ctx = _FakeCtx(str(tmp_path))
        srt_rel = "srt/task_t/missing.srt"
        with pytest.raises(AsrError):
            transcribe(ctx, "audio/task_t/nope.wav", srt_rel,
                       AsrConfig(strategy="single", engine="whisper_cpp", whisper_model_path="/tmp/x"))
        assert not (tmp_path / srt_rel).exists()


# ----------------------------- 在线整段 vs 本地 VAD 分流（optimize-asr-throughput）----------------------------- #


class TestLongAudioVadSplit:
    """长音频一律 VAD 分段并行（design D1 修订：bcut 整段上限 ~6min，长音频整段必失败）。"""

    def _long_wav(self, tmp_path):
        p = tmp_path / "long.wav"
        p.write_bytes(b"fake-audio-bytes")
        return str(p)

    def test_online_long_audio_uses_vad_split(self, tmp_path, monkeypatch):
        """在线引擎 + 长音频 → VAD 分段（不再整段尝试，避免整段上限浪费）。"""
        monkeypatch.setattr(P, "get_audio_duration_seconds", lambda p: 7200.0)
        split = {"called": False}
        wav = self._long_wav(tmp_path)
        monkeypatch.setattr(P, "split_audio_by_silence",
                            lambda *a, **k: split.__setitem__("called", True) or [AudioSegment(0, 60, wav)])
        monkeypatch.setattr(P, "build_engines",
                            lambda cfg: {"bcut": _StubOnline(), "whisper_cpp": _StubLocal()})
        P.transcribe_audio(wav, AsrConfig(strategy="online_first", engine="bcut"))
        assert split["called"] is True

    def test_online_profile_uses_mp3_280_seconds_and_configured_workers(self, tmp_path, monkeypatch):
        monkeypatch.setattr(P, "get_audio_duration_seconds", lambda p: 7200.0)
        wav = self._long_wav(tmp_path)
        captured = {}

        def fake_split(*args, **kwargs):
            captured.update(kwargs)
            return [
                AudioSegment(0, 280, wav),
                AudioSegment(280, 280, wav),
                AudioSegment(560, 280, wav),
            ]

        monkeypatch.setattr(P, "split_audio_by_silence", fake_split)
        monkeypatch.setattr(P, "build_engines", lambda cfg: {"bcut": _StubOnline()})
        metrics = {}
        P.transcribe_audio(
            wav,
            AsrConfig(
                strategy="single",
                engine="bcut",
                cache_enabled=False,
                online_concurrency=3,
            ),
            metrics=metrics,
        )
        assert captured["output_format"] == "mp3"
        assert captured["target_segment_sec"] == 280
        assert captured["max_segment_sec"] == 295
        assert metrics["worker_count"] == 3

    def test_local_profile_uses_wav_and_one_worker(self, tmp_path, monkeypatch):
        monkeypatch.setattr(P, "get_audio_duration_seconds", lambda p: 7200.0)
        wav = self._long_wav(tmp_path)
        captured = {}

        def fake_split(*args, **kwargs):
            captured.update(kwargs)
            return [AudioSegment(0, 120, wav), AudioSegment(120, 120, wav)]

        monkeypatch.setattr(P, "split_audio_by_silence", fake_split)
        monkeypatch.setattr(P, "build_engines", lambda cfg: {"whisper_cpp": _StubLocal()})
        metrics = {}
        P.transcribe_audio(
            wav,
            AsrConfig(strategy="single", engine="whisper_cpp", cache_enabled=False),
            metrics=metrics,
        )
        assert captured["output_format"] == "wav"
        assert captured["target_segment_sec"] == 120
        assert metrics["worker_count"] == 1

    def test_local_long_audio_uses_vad_split(self, tmp_path, monkeypatch):
        """本地引擎 + 长音频 → VAD 分段并行。"""
        monkeypatch.setattr(P, "get_audio_duration_seconds", lambda p: 7200.0)
        split = {"called": False}
        wav = self._long_wav(tmp_path)
        monkeypatch.setattr(P, "split_audio_by_silence",
                            lambda *a, **k: split.__setitem__("called", True) or [AudioSegment(0, 60, wav)])
        monkeypatch.setattr(P, "build_engines", lambda cfg: {"whisper_cpp": _StubLocal()})
        P.transcribe_audio(wav, AsrConfig(strategy="single", engine="whisper_cpp"))
        assert split["called"] is True


# ----------------------------- crc32 文件级缓存（optimize-asr-throughput）----------------------------- #


class _StubBcutClient:
    """绕过真实 HTTP 的 bcut 客户端：上传计数、result 立即返回完成。"""
    def __init__(self, timeout, session=None, payload_text="缓存测试"):
        self._payload = payload_text
    def upload(self, binary, file_ext="mp3"):
        _StubBcutClient.uploads += 1
    def create_task(self):
        return "tid"
    def result(self):
        return {"state": 4, "result": '{"utterances":[{"start_time":0,"end_time":1000,"transcript":"%s"}]}' % self._payload}


class TestAsrCache:
    def test_cache_hit_skips_second_upload(self, tmp_path, monkeypatch):
        from src.speech_to_text import bcut as bcut_mod
        _StubBcutClient.uploads = 0
        monkeypatch.setattr(bcut_mod, "_BcutClient", _StubBcutClient)
        wav = tmp_path / "a.wav"
        wav.write_bytes(b"\x01\x02\x03\x04")
        eng = BcutEngine(cache_enabled=True, cache_dir=str(tmp_path / "cache"))
        first = eng.transcribe(str(wav))
        second = eng.transcribe(str(wav))  # 命中缓存，跳过上传
        assert _StubBcutClient.uploads == 1
        assert first == second
        assert first[0].text == "缓存测试"

    def test_different_audio_not_cached(self, tmp_path, monkeypatch):
        from src.speech_to_text import bcut as bcut_mod
        _StubBcutClient.uploads = 0
        monkeypatch.setattr(bcut_mod, "_BcutClient", _StubBcutClient)
        a = tmp_path / "a.wav"; a.write_bytes(b"\x01\x02")
        b = tmp_path / "b.wav"; b.write_bytes(b"\x03\x04\x05")
        eng = BcutEngine(cache_enabled=True, cache_dir=str(tmp_path / "cache"))
        eng.transcribe(str(a))
        eng.transcribe(str(b))
        assert _StubBcutClient.uploads == 2

    def test_cache_disabled_uploads_both(self, tmp_path, monkeypatch):
        from src.speech_to_text import bcut as bcut_mod
        _StubBcutClient.uploads = 0
        monkeypatch.setattr(bcut_mod, "_BcutClient", _StubBcutClient)
        wav = tmp_path / "a.wav"
        wav.write_bytes(b"\x01\x02\x03")
        eng = BcutEngine(cache_enabled=False, cache_dir=str(tmp_path / "cache"))
        eng.transcribe(str(wav))
        eng.transcribe(str(wav))
        assert _StubBcutClient.uploads == 2

    def test_whole_audio_cache_hits_before_duration_probe_and_vad(self, tmp_path, monkeypatch):
        wav = tmp_path / "whole.wav"
        wav.write_bytes(b"whole-audio-content")
        calls = {"duration": 0, "split": 0, "transcribe": 0}

        class CountingOnline(_StubOnline):
            def transcribe(self, audio_path, on_progress=None):
                calls["transcribe"] += 1
                return super().transcribe(audio_path, on_progress)

        def duration(_path):
            calls["duration"] += 1
            return 7200.0

        def split(*_args, **_kwargs):
            calls["split"] += 1
            return [AudioSegment(0, 60, str(wav))]

        monkeypatch.setattr(P, "get_audio_duration_seconds", duration)
        monkeypatch.setattr(P, "split_audio_by_silence", split)
        monkeypatch.setattr(P, "build_engines", lambda cfg: {"bcut": CountingOnline()})
        cfg = AsrConfig(
            strategy="single",
            engine="bcut",
            cache_enabled=True,
            cache_dir=str(tmp_path / "whole-cache"),
        )
        cold_metrics = {}
        warm_metrics = {}
        first = P.transcribe_audio(str(wav), cfg, metrics=cold_metrics)
        second = P.transcribe_audio(str(wav), cfg, metrics=warm_metrics)
        assert first == second
        assert calls == {"duration": 1, "split": 1, "transcribe": 1}
        assert cold_metrics["cache_hit"] is False
        assert warm_metrics["cache_hit"] is True
        assert warm_metrics["segment_count"] == 0

    def test_corrupt_whole_cache_falls_back_to_cold_transcription(self, tmp_path, monkeypatch):
        wav = tmp_path / "corrupt.wav"
        wav.write_bytes(b"corrupt-cache-audio")
        calls = {"transcribe": 0}

        class CountingOnline(_StubOnline):
            def transcribe(self, audio_path, on_progress=None):
                calls["transcribe"] += 1
                return super().transcribe(audio_path, on_progress)

        monkeypatch.setattr(P, "get_audio_duration_seconds", lambda _p: 3.0)
        monkeypatch.setattr(P, "build_engines", lambda cfg: {"bcut": CountingOnline()})
        cache_dir = tmp_path / "whole-cache"
        cfg = AsrConfig(strategy="single", engine="bcut", cache_enabled=True, cache_dir=str(cache_dir))
        P.transcribe_audio(str(wav), cfg)
        cache_file = next(cache_dir.glob("whole-v2-*.json"))
        cache_file.write_text("{broken", encoding="utf-8")
        metrics = {}
        P.transcribe_audio(str(wav), cfg, metrics=metrics)
        assert calls["transcribe"] == 2
        assert metrics["cache_hit"] is False


class TestBcutRollingBudget:
    def test_reservation_blocks_then_recovers_after_rolling_window(self, tmp_path):
        cache_dir = str(tmp_path / "budget")
        first = BB.reserve(cache_dir, calls=60, audio_seconds=10_000, now=100_000)
        blocked = BB.reserve(cache_dir, calls=41, audio_seconds=1_000, now=100_001)
        recovered = BB.reserve(
            cache_dir,
            calls=41,
            audio_seconds=1_000,
            now=100_000 + BB.WINDOW_SECONDS + 1,
        )
        assert first.allowed is True
        assert blocked.allowed is False
        assert blocked.retry_after_seconds > 0
        assert recovered.allowed is True

    def test_corrupt_budget_fails_closed(self, tmp_path):
        cache_dir = tmp_path / "budget"
        cache_dir.mkdir()
        (cache_dir / "bcut-budget-v1.json").write_text("{broken", encoding="utf-8")
        decision = BB.reserve(str(cache_dir), calls=1, audio_seconds=30)
        assert decision.allowed is False
        assert decision.tracked is False
        assert decision.reason == "tracking_unavailable"

    def test_remote_rate_limit_cooldown_persists_and_expires(self, tmp_path, monkeypatch):
        cache_dir = str(tmp_path / "budget")
        BB.mark_rate_limited(cache_dir, now=100_000)

        # 模拟容器内模块状态丢失，确保下一次判断来自持久化冷却文件。
        monkeypatch.setattr(BB, "_PROCESS_COOLDOWN_UNTIL", 0.0)
        blocked = BB.reserve(cache_dir, calls=1, audio_seconds=30, now=100_001)
        recovered = BB.reserve(
            cache_dir,
            calls=1,
            audio_seconds=30,
            now=100_000 + BB.WINDOW_SECONDS + 1,
        )

        assert blocked.allowed is False
        assert blocked.reason == "remote_rate_limited"
        assert blocked.retry_after_seconds == pytest.approx(BB.WINDOW_SECONDS - 1)
        assert recovered.allowed is True

    def test_exhausted_budget_switches_whole_task_to_local_profile(
        self, tmp_path, monkeypatch
    ):
        cache_dir = str(tmp_path / "budget")
        assert BB.reserve(cache_dir, calls=100, audio_seconds=1).allowed
        wav = tmp_path / "long.wav"
        wav.write_bytes(b"fake-audio")
        attempts = {"bcut": 0, "local": 0}
        captured = {}

        class CountingOnline(_StubOnline):
            def transcribe(self, audio_path, on_progress=None):
                attempts["bcut"] += 1
                return super().transcribe(audio_path, on_progress)

        class CountingLocal(_StubLocal):
            def transcribe(self, audio_path, on_progress=None):
                attempts["local"] += 1
                return super().transcribe(audio_path, on_progress)

        def fake_split(*args, **kwargs):
            captured.update(kwargs)
            return [AudioSegment(0, 120, str(wav)), AudioSegment(120, 120, str(wav))]

        monkeypatch.setattr(P, "get_audio_duration_seconds", lambda _p: 7200.0)
        monkeypatch.setattr(P, "split_audio_by_silence", fake_split)
        monkeypatch.setattr(
            P,
            "build_engines",
            lambda _cfg: {"bcut": CountingOnline(), "whisper_cpp": CountingLocal()},
        )
        metrics = {}
        P.transcribe_audio(
            str(wav),
            AsrConfig(
                strategy="online_first",
                engine="bcut",
                cache_enabled=False,
                cache_dir=cache_dir,
            ),
            metrics=metrics,
        )
        assert attempts == {"bcut": 0, "local": 2}
        assert captured["output_format"] == "wav"
        assert metrics["engine_order"] == ["whisper_cpp"]
        assert metrics["worker_count"] == 1
        assert metrics["bcut_budget_allowed"] is False


class TestAsrRuntimeCoordination:
    def test_online_long_audio_probes_once_before_rate_limit_fallback(
        self, tmp_path, monkeypatch
    ):
        wav = tmp_path / "long.wav"
        wav.write_bytes(b"fake-audio")
        attempts = {"bcut": 0, "local": 0}

        class SlowRateLimited(_StubOnline):
            def transcribe(self, audio_path, on_progress=None):
                attempts["bcut"] += 1
                time.sleep(0.05)
                raise AsrError(
                    "远端限流", reason="rate_limited", engine="bcut", status_code=412
                )

        class CountingLocal(_StubLocal):
            def transcribe(self, audio_path, on_progress=None):
                attempts["local"] += 1
                return super().transcribe(audio_path, on_progress)

        monkeypatch.setattr(P, "get_audio_duration_seconds", lambda _path: 840.0)
        monkeypatch.setattr(
            P,
            "split_audio_by_silence",
            lambda *_args, **_kwargs: [
                AudioSegment(0, 280, str(wav)),
                AudioSegment(280, 280, str(wav)),
                AudioSegment(560, 280, str(wav)),
            ],
        )
        monkeypatch.setattr(
            P,
            "build_engines",
            lambda _cfg: {"bcut": SlowRateLimited(), "whisper_cpp": CountingLocal()},
        )
        metrics = {}
        P.transcribe_audio(
            str(wav),
            AsrConfig(
                strategy="online_first",
                engine="bcut",
                cache_enabled=False,
                online_concurrency=3,
            ),
            metrics=metrics,
        )

        assert attempts == {"bcut": 1, "local": 3}
        assert metrics["degradation_count"] == 1
        assert metrics["online_probe_used"] is True
        assert metrics["worker_count"] == 1

    def test_local_whisper_is_exclusive_across_resolvers(self):
        state = {"active": 0, "max_active": 0}
        state_lock = threading.Lock()

        class SlowLocal(_StubLocal):
            def transcribe(self, audio_path, on_progress=None):
                with state_lock:
                    state["active"] += 1
                    state["max_active"] = max(state["max_active"], state["active"])
                try:
                    time.sleep(0.08)
                    return super().transcribe(audio_path, on_progress)
                finally:
                    with state_lock:
                        state["active"] -= 1

        resolvers = [
            P._EngineResolver(
                {"whisper_cpp": SlowLocal()}, ["whisper_cpp"], strategy="single"
            )
            for _ in range(2)
        ]

        def run(resolver):
            try:
                return resolver.transcribe("segment.wav")
            finally:
                resolver.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, resolvers))

        assert all(result[0].text == "本地字幕" for result in results)
        assert state["max_active"] == 1

    def test_waiting_for_local_slot_can_be_cancelled(self):
        holder = P._EngineResolver(
            {"whisper_cpp": _StubLocal()}, ["whisper_cpp"], strategy="single"
        )
        holder.transcribe("holder.wav")
        cancelled = threading.Event()
        waiter = P._EngineResolver(
            {"whisper_cpp": _StubLocal()},
            ["whisper_cpp"],
            strategy="single",
            is_cancelled=cancelled.is_set,
        )

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(waiter.transcribe, "waiter.wav")
            time.sleep(0.05)
            cancelled.set()
            with pytest.raises(P.CancelledError):
                future.result(timeout=1)

        holder.close()
        waiter.close()

    def test_local_slot_is_released_after_task_exception(self):
        class BrokenLocal(_StubLocal):
            def transcribe(self, audio_path, on_progress=None):
                raise AsrError("本地失败", reason="unknown", engine="whisper_cpp")

        broken = P._EngineResolver(
            {"whisper_cpp": BrokenLocal()}, ["whisper_cpp"], strategy="single"
        )
        with pytest.raises(AsrError):
            try:
                broken.transcribe("broken.wav")
            finally:
                broken.close()

        healthy = P._EngineResolver(
            {"whisper_cpp": _StubLocal()}, ["whisper_cpp"], strategy="single"
        )
        try:
            assert healthy.transcribe("healthy.wav")[0].text == "本地字幕"
        finally:
            healthy.close()


class TestOnlineTransport:
    def test_vad_can_emit_16khz_mono_mp3(self, short_wav, tmp_path):
        out = tmp_path / "segment_0000.mp3"
        assert V._extract_segment(
            short_wav,
            0,
            2,
            str(out),
            output_format="mp3",
            bitrate_kbps=64,
        )
        assert out.exists() and out.stat().st_size > 0
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "a:0",
                "-show_entries", "stream=sample_rate,channels",
                "-of", "default=noprint_wrappers=1", str(out),
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert "sample_rate=16000" in probe
        assert "channels=1" in probe

    def test_bcut_reuses_one_session_per_worker(self, monkeypatch):
        from src.speech_to_text import bcut as bcut_mod

        sessions = []

        def build_session():
            session = object()
            sessions.append(session)
            return session

        monkeypatch.setattr(bcut_mod, "_build_session", build_session)
        engine = BcutEngine(cache_enabled=False)
        assert engine._worker_session() is engine._worker_session()
        assert len(sessions) == 1

    def test_bcut_poll_backoff_is_capped_at_four_seconds(self, tmp_path, monkeypatch):
        from src.speech_to_text import bcut as bcut_mod

        sleeps = []

        class PollClient:
            def __init__(self, timeout, session=None):
                self.results = 0
            def upload(self, binary, file_ext="mp3"):
                return None
            def create_task(self):
                return "tid"
            def result(self):
                self.results += 1
                if self.results < 4:
                    return {"state": 1}
                return {"state": 4, "result": '{"utterances":[]}'}

        monkeypatch.setattr(bcut_mod, "_BcutClient", PollClient)
        monkeypatch.setattr(bcut_mod.time, "sleep", lambda seconds: sleeps.append(seconds))
        monkeypatch.setattr(bcut_mod.random, "uniform", lambda _a, _b: 0)
        wav = tmp_path / "poll.wav"
        wav.write_bytes(b"audio")
        BcutEngine(cache_enabled=False, query_interval=2).transcribe(str(wav))
        assert sleeps == [2, 4, 4]

    def test_bcut_does_not_retry_rate_limited_response(self, tmp_path, monkeypatch):
        from src.speech_to_text import bcut as bcut_mod

        sessions = []

        class Session:
            def __init__(self, index):
                self.index = index
            def close(self):
                return None

        def build_session():
            session = Session(len(sessions) + 1)
            sessions.append(session)
            return session

        class RateLimitedClient:
            def __init__(self, timeout, session=None):
                self.session = session
            def upload(self, binary, file_ext="mp3"):
                raise AsrError(
                    "滚动额度不足", reason="rate_limited", engine="bcut", status_code=412
                )
            def create_task(self):
                return "tid"
            def result(self):
                return {"state": 4, "result": '{"utterances":[]}'}

        monkeypatch.setattr(bcut_mod, "_build_session", build_session)
        monkeypatch.setattr(bcut_mod, "_BcutClient", RateLimitedClient)
        wav = tmp_path / "rotate.wav"
        wav.write_bytes(b"audio")
        engine = BcutEngine(cache_enabled=False, max_retries=1)
        with pytest.raises(AsrError) as exc:
            engine.transcribe(str(wav))
        assert exc.value.status_code == 412
        assert len(sessions) == 1
        assert engine.metrics_snapshot()["retry_count"] == 0


class TestResilience:
    """长视频分段 ASR 韧性：bcut 间歇失败不全局塌方到 whisper + bcut 内部重试。"""

    def test_online_failure_does_not_globally_disable_bcut(self):
        """bcut 单段失败：该段降级 whisper，但下一段仍尝试 bcut（不永久锁定 whisper）。"""
        attempts = {"bcut": 0}

        class FlakyBcut(AsrEngine):
            name = "bcut"
            def transcribe(self, ap, on_progress=None):
                attempts["bcut"] += 1
                if attempts["bcut"] == 1:
                    raise AsrError("间歇失败", reason="invalid_response", engine="bcut")
                return [Cue(0.0, 1.0, "bcut 段")]

        engines = {"bcut": FlakyBcut(), "whisper_cpp": _StubLocal()}
        resolver = P._EngineResolver(engines, ["bcut", "whisper_cpp"], strategy="online_first")
        cues1 = resolver.transcribe("a.wav")   # 第 1 段 bcut 失败 → whisper 兜底
        assert cues1[0].text == "本地字幕"
        cues2 = resolver.transcribe("a.wav")   # 第 2 段仍试 bcut（未永久禁用）→ 成功
        assert cues2[0].text == "bcut 段"
        assert attempts["bcut"] == 2

    def test_bcut_retries_intermittent_failure(self, tmp_path, monkeypatch):
        """bcut 单段失败时内部重试，重试成功则不降级。"""
        from src.speech_to_text import bcut as bcut_mod
        attempts = {"upload": 0}

        class RetryClient:
            def __init__(self, timeout, session=None): pass
            def upload(self, binary, file_ext="mp3"):
                attempts["upload"] += 1
                if attempts["upload"] == 1:
                    raise AsrError("间歇", reason="invalid_response", engine="bcut")
            def create_task(self): return "tid"
            def result(self):
                return {"state": 4, "result": '{"utterances":[{"start_time":0,"end_time":1000,"transcript":"重试成功"}]}'}

        monkeypatch.setattr(bcut_mod, "_BcutClient", RetryClient)
        wav = tmp_path / "a.wav"; wav.write_bytes(b"\x01\x02\x03")
        eng = BcutEngine(cache_enabled=False, max_retries=2)
        cues = eng.transcribe(str(wav))
        assert cues[0].text == "重试成功"
        assert attempts["upload"] == 2  # 第 1 次失败 + 重试成功
