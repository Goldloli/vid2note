"""测试 ASR 设备检测

torch 为可选依赖（CPU-only 环境/Docker CPU 镜像未安装）。
torch 未安装时 detect_device 应返回 "cpu"；
torch 已安装时测试 mps/cuda 回退逻辑（用 fake module 注入）。
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from vid2note_core.asr.local.device import detect_device


def test_detect_device_returns_valid():
    device = detect_device()
    assert device in ["cuda", "mps", "cpu"]


def test_detect_cpu_when_no_torch(monkeypatch):
    """torch 未安装时 detect_device 应返回 cpu（不抛异常）。

    本地可能装了 torch；通过 monkeypatch 让 import torch 抛 ImportError 来模拟未安装。
    """
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "torch":
            raise ModuleNotFoundError("No module named 'torch'")
        return real_import(name, *args, **kwargs)

    # 清除已缓存的 torch 模块，强制重新 import
    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.delitem(sys.modules, "torch", raising=False)
    assert detect_device() == "cpu"


def test_detect_cpu_fallback(monkeypatch):
    """torch 已安装但 cuda/mps 都不可用时返回 cpu。

    用注入 fake torch 模块的方式，避免对真实 torch 的硬依赖。
    """
    fake = ModuleType("torch")
    fake.cuda = MagicMock()
    fake.cuda.is_available = MagicMock(return_value=False)
    fake.backends = MagicMock()
    fake.backends.mps = MagicMock()
    fake.backends.mps.is_available = MagicMock(return_value=False)
    monkeypatch.setitem(sys.modules, "torch", fake)
    assert detect_device() == "cpu"


def test_detect_cuda(monkeypatch):
    """cuda 可用时返回 cuda。"""
    fake = ModuleType("torch")
    fake.cuda = MagicMock()
    fake.cuda.is_available = MagicMock(return_value=True)
    monkeypatch.setitem(sys.modules, "torch", fake)
    assert detect_device() == "cuda"


def test_detect_mps(monkeypatch):
    """cuda 不可用但 mps 可用时返回 mps。"""
    fake = ModuleType("torch")
    fake.cuda = MagicMock()
    fake.cuda.is_available = MagicMock(return_value=False)
    fake.backends = MagicMock()
    fake.backends.mps = MagicMock()
    fake.backends.mps.is_available = MagicMock(return_value=True)
    monkeypatch.setitem(sys.modules, "torch", fake)
    assert detect_device() == "mps"
