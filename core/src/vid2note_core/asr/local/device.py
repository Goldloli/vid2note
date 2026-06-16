"""设备检测

torch 采用延迟导入：CPU-only 环境（如 Docker CPU 镜像）未安装 torch 时，
detect_device 直接返回 "cpu"，不影响服务启动。
"""

from typing import Literal


def detect_device() -> Literal["cuda", "mps", "cpu"]:
    try:
        import torch
    except ImportError:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"
