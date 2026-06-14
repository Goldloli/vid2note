"""外部二进制管理"""
import os
import shutil
from pathlib import Path
from typing import Optional


class BinaryManager:
    def __init__(self, name: str):
        self.name = name

    def resolve(self) -> Path:
        # 1. 环境变量
        env = os.environ.get(f"VID2NOTE_{self.name.upper()}_PATH")
        if env:
            p = Path(env)
            if p.exists():
                return p

        # 2. 内置资源目录（Electron）
        resources = os.environ.get("VID2NOTE_RESOURCES_DIR")
        if resources:
            p = Path(resources) / self.name
            if p.exists():
                return p

        # 3. 系统 PATH
        system = shutil.which(self.name)
        if system:
            return Path(system)

        raise FileNotFoundError(f"未找到二进制: {self.name}")
