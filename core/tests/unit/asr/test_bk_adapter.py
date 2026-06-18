"""测试 BkAsrAdapter（基于 bk_asr 的云端 ASR 适配器）。

用 monkeypatch 替换 bk_asr 的真实 HTTP 调用，验证适配层逻辑。
"""

import pytest
from vid2note_core.asr.cloud.bk_adapter import BkAsrAdapter
from vid2note_core.errors import ASRError


class _FakeSegment:
    """模拟 bk_asr 的 segment 对象。"""

    def __init__(self, text: str, start_time: int, end_time: int):
        self.text = text
        self.start_time = start_time
        self.end_time = end_time


class _FakeASRData:
    """模拟 bk_asr 的 run() 返回对象。"""

    def __init__(self, segments):
        self.segments = segments


class _FakeBackend:
    """模拟 BcutASR/JianYingASR/KuaiShouASR 类。"""

    def __init__(self, audio_path, use_cache=False):
        self.audio_path = audio_path
        self.use_cache = use_cache

    def run(self):
        return _FakeASRData(
            segments=[
                _FakeSegment("你好世界", 0, 1500),
                _FakeSegment("测试识别", 1500, 3000),
                _FakeSegment("", 3000, 3500),  # 空文本应被跳过
            ]
        )


def test_unsupported_backend_raises():
    with pytest.raises(ValueError, match="不支持的 bk_asr 后端"):
        BkAsrAdapter(backend="invalid")


def test_vendored_backend_is_not_bundled():
    with pytest.raises(ValueError, match="不支持的 bk_asr 后端"):
        BkAsrAdapter()


def test_transcribe_maps_segments(tmp_path, monkeypatch):
    """验证 bk_asr 返回的 segments 正确映射为 ASRResult。"""
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"fake audio")

    # patch _BACKENDS dict（adapter 在 __init__ 时从中取 backend_cls）
    import vid2note_core.asr.cloud.bk_adapter as mod

    monkeypatch.setitem(mod._BACKENDS, "bcut", _FakeBackend)

    asr = BkAsrAdapter(backend="bcut")
    assert asr.backend_cls is _FakeBackend
    result = asr.transcribe(audio, {"language": "zh"})

    assert result.language == "zh"
    assert len(result.segments) == 2  # 空文本 segment 被跳过
    assert result.segments[0].text == "你好世界"
    assert result.segments[0].start_ms == 0
    assert result.segments[1].start_ms == 1500
    assert result.text_full == "你好世界测试识别"
    assert result.duration_ms == 3000


def test_transcribe_missing_file_raises(tmp_path, monkeypatch):
    import vid2note_core.asr.cloud.bk_adapter as mod

    monkeypatch.setitem(mod._BACKENDS, "bcut", _FakeBackend)
    asr = BkAsrAdapter(backend="bcut")
    with pytest.raises(ASRError, match="音频文件不存在"):
        asr.transcribe(tmp_path / "nope.wav", {"language": "zh"})


def test_transcribe_backend_failure_wraps_asr_error(tmp_path, monkeypatch):
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"fake")

    class _CrashingBackend(_FakeBackend):
        def run(self):
            raise ConnectionError("upstream down")

    import vid2note_core.asr.cloud.bk_adapter as mod

    monkeypatch.setitem(mod._BACKENDS, "bcut", _CrashingBackend)

    asr = BkAsrAdapter(backend="bcut")
    with pytest.raises(ASRError, match="bk_asr .* 识别失败"):
        asr.transcribe(audio, {"language": "zh"})


def test_ensure_readable_renames_bad_suffix(tmp_path):
    """后缀不在白名单时应重命名为 .wav。"""
    bad = tmp_path / "audio.dat"
    bad.write_bytes(b"fake")
    renamed = BkAsrAdapter._ensure_readable(bad)
    assert renamed.suffix == ".wav"
    assert renamed.exists()
    assert not bad.exists()
