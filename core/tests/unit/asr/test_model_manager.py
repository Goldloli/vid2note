"""测试模型管理器"""

import pytest
from vid2note_core.asr.local.model_manager import ModelManager
from vid2note_core.errors import ASRModelNotFound


def test_list_available():
    mgr = ModelManager()
    models = mgr.list_available()
    assert len(models) >= 4
    ids = [m["id"] for m in models]
    assert "funasr-paraformer-small" in ids


def test_get_path_missing():
    mgr = ModelManager()
    with pytest.raises(ASRModelNotFound):
        mgr.get_path("nonexistent-model")


def test_list_installed_empty(tmp_path):
    mgr = ModelManager(base_dir=tmp_path)
    assert mgr.list_installed() == []
