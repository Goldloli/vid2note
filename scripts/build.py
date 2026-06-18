#!/usr/bin/env python3
"""
PyInstaller 打包脚本：将 vid2note Python 后端打包为独立目录
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DIST_DIR = ROOT / "python-dist"
SPEC_FILE = ROOT / "scripts" / "vid2note.spec"


def build():
    """运行 PyInstaller 打包"""
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--distpath",
        str(DIST_DIR),
        str(SPEC_FILE),
    ]
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print(f"Build complete: {DIST_DIR}")


if __name__ == "__main__":
    build()
