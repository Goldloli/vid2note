"""测试 Qwen3-ASR 适配器"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from vid2note_core.asr.base import ASRResult
from vid2note_core.asr.local.model_manager import ModelManager
from vid2note_core.asr.local.qwen_asr import Qwen3ASRAdapter
from vid2note_core.errors import ASRError


def _make_mock_factories(result_text: str = "你好世界"):
    """构造假的 processor/model 工厂。"""
    mock_processor = MagicMock()
    mock_model = MagicMock()
    # processor() 返回带 input_ids 的 dict-like，可链式调用 .to()
    mock_inputs_obj = MagicMock()
    mock_inputs_obj.__getitem__ = lambda self, k: MagicMock(shape=[1, 5])
    mock_inputs_obj.__contains__ = lambda self, k: k == "input_ids"
    mock_processor.return_value = mock_inputs_obj
    # model.generate 返回 tensor-like [[tokens...]]
    mock_output = MagicMock()
    mock_output.__getitem__ = lambda self, idx: mock_output
    mock_output.shape = [1, 5]
    mock_model.generate.return_value = mock_output
    # processor.batch_decode 返回 [result_text]
    mock_processor.batch_decode.return_value = [result_text]

    proc_factory = MagicMock()
    proc_factory.from_pretrained.return_value = mock_processor
    model_factory = MagicMock()
    model_factory.from_pretrained.return_value = mock_model

    return proc_factory, model_factory, mock_processor, mock_model


def test_qwen3asr_not_available_without_model(tmp_path):
    asr = Qwen3ASRAdapter(model_manager=ModelManager(tmp_path))
    assert asr.is_available() is False


def test_qwen3asr_name(tmp_path):
    asr = Qwen3ASRAdapter(model_manager=ModelManager(tmp_path))
    assert asr.name == "qwen3-asr"


def test_qwen3asr_transcribe_success(tmp_path):
    """注入 mock 工厂，验证 transcribe 返回 ASRResult"""
    proc_f, model_f, mock_proc, mock_model = _make_mock_factories("转录结果文本")
    asr = Qwen3ASRAdapter(
        model_manager=ModelManager(tmp_path),
        processor_factory=proc_f,
        model_factory=model_f,
    )

    result = asr.transcribe(Path("/fake/audio.wav"), {"language": "zh"})

    assert isinstance(result, ASRResult)
    assert result.text_full == "转录结果文本"
    assert len(result.segments) == 1
    assert result.segments[0].text == "转录结果文本"
    assert result.language == "zh"
    mock_model.generate.assert_called_once()


def test_qwen3asr_transcribe_english(tmp_path):
    proc_f, model_f, _, mock_model = _make_mock_factories("hello world")
    asr = Qwen3ASRAdapter(
        model_manager=ModelManager(tmp_path),
        processor_factory=proc_f,
        model_factory=model_f,
    )
    result = asr.transcribe(Path("/fake/audio.wav"), {"language": "en"})
    assert result.text_full == "hello world"
    assert result.language == "en"


def test_qwen3asr_model_load_failure(tmp_path):
    """模型加载失败 → ASRError"""
    proc_f = MagicMock()
    proc_f.from_pretrained.side_effect = RuntimeError("model not found")
    asr = Qwen3ASRAdapter(
        model_manager=ModelManager(tmp_path),
        processor_factory=proc_f,
        model_factory=MagicMock(),
    )
    with pytest.raises(ASRError) as exc_info:
        asr.transcribe(Path("/fake/audio.wav"), {})
    assert exc_info.value.code == "ASR_MODEL_LOAD_FAILED"


def test_qwen3asr_infer_failure(tmp_path):
    """推理失败 → ASRError（可重试）"""
    proc_f, model_f, _, mock_model = _make_mock_factories()
    mock_model.generate.side_effect = RuntimeError("infer failed")
    asr = Qwen3ASRAdapter(
        model_manager=ModelManager(tmp_path),
        processor_factory=proc_f,
        model_factory=model_f,
    )
    with pytest.raises(ASRError) as exc_info:
        asr.transcribe(Path("/fake/audio.wav"), {})
    assert exc_info.value.code == "ASR_INFER_FAILED"
    assert exc_info.value.retryable is True


def test_qwen3asr_available_with_local_model(tmp_path):
    """本地已安装模型时 is_available 返回 True"""
    (tmp_path / "qwen3-asr-base").mkdir()
    asr = Qwen3ASRAdapter(model_manager=ModelManager(tmp_path))
    assert asr.is_available() is True
