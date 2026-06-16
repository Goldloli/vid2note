"""测试 FunASR 适配器"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from vid2note_core.asr.base import ASRResult
from vid2note_core.asr.local.funasr import FunASRAdapter
from vid2note_core.errors import ASRError


def _make_mock_factory(result: list[dict]):
    """构造一个假的 AutoModel 工厂，generate 返回 result。"""
    mock_model = MagicMock()
    mock_model.generate.return_value = result
    factory = MagicMock(return_value=mock_model)
    return factory, mock_model


def test_funasr_not_available_without_model():
    asr = FunASRAdapter()
    assert asr.is_available() is False


def test_funasr_name():
    asr = FunASRAdapter()
    assert asr.name == "funasr"


def test_funasr_transcribe_success():
    """注入 mock AutoModel，验证 transcribe 正确解析输出为 ASRResult"""
    result = [{"text": "你好世界", "timestamp": [[0], [1500]]}]
    factory, mock_model = _make_mock_factory(result)
    asr = FunASRAdapter(auto_model_factory=factory)

    out = asr.transcribe(Path("/fake/audio.wav"), {"language": "zh"})

    assert isinstance(out, ASRResult)
    assert out.text_full == "你好世界"
    assert len(out.segments) == 1
    assert out.segments[0].start_ms == 0
    assert out.segments[0].end_ms == 1500
    assert out.language == "zh"
    mock_model.generate.assert_called_once()


def test_funasr_transcribe_no_timestamp():
    """无 timestamp 的输出退化为 0-0 段"""
    result = [{"text": "纯文本"}]
    factory, _ = _make_mock_factory(result)
    asr = FunASRAdapter(auto_model_factory=factory)
    out = asr.transcribe(Path("/fake/audio.wav"), {"language": "zh"})
    assert out.text_full == "纯文本"
    assert out.segments[0].start_ms == 0
    assert out.segments[0].end_ms == 0


def test_funasr_transcribe_empty_result():
    factory, _ = _make_mock_factory([])
    asr = FunASRAdapter(auto_model_factory=factory)
    out = asr.transcribe(Path("/fake/audio.wav"), {"language": "zh"})
    assert out.text_full == ""
    assert out.segments == []


def test_funasr_transcribe_english_uses_space_join():
    result = [{"text": "hello"}, {"text": "world"}]
    factory, _ = _make_mock_factory(result)
    asr = FunASRAdapter(auto_model_factory=factory)
    out = asr.transcribe(Path("/fake/audio.wav"), {"language": "en"})
    assert out.text_full == "hello world"
    assert out.language == "en"


def test_funasr_model_load_failure_raises_asr_error():
    """模型加载失败应转为 ASRError"""
    factory = MagicMock(side_effect=RuntimeError("model not found"))
    asr = FunASRAdapter(auto_model_factory=factory)
    with pytest.raises(ASRError) as exc_info:
        asr.transcribe(Path("/fake/audio.wav"), {})
    assert exc_info.value.code == "ASR_MODEL_LOAD_FAILED"


def test_funasr_infer_failure_raises_asr_error():
    """推理失败应转为 ASRError（可重试）"""
    mock_model = MagicMock()
    mock_model.generate.side_effect = RuntimeError("infer failed")
    factory = MagicMock(return_value=mock_model)
    asr = FunASRAdapter(auto_model_factory=factory)
    with pytest.raises(ASRError) as exc_info:
        asr.transcribe(Path("/fake/audio.wav"), {})
    assert exc_info.value.code == "ASR_INFER_FAILED"
    assert exc_info.value.retryable is True


def test_funasr_available_with_local_model(tmp_path, monkeypatch):
    """本地已安装模型时 is_available 返回 True"""
    from vid2note_core.asr.local import model_manager as mm

    monkeypatch.setattr(mm.ModelManager, "_default_dir", lambda self: str(tmp_path))
    (tmp_path / "funasr-paraformer-small").mkdir()
    asr = FunASRAdapter()
    assert asr.is_available() is True


def test_funasr_factory_registers():
    """ASRFactory 应能创建 funasr provider"""
    from vid2note_core.asr.factory import ASRFactory

    asr = ASRFactory.create("funasr", {})
    assert isinstance(asr, FunASRAdapter)
    assert "funasr" in ASRFactory.get_available_providers()
