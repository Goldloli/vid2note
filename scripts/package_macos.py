#!/usr/bin/env python3
"""
打包 Electron + Python 为完整 macOS 应用。
步骤：
1. 拉取二进制工具
2. PyInstaller 打包 Python 后端
3. Electron Builder 打包桌面应用
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def run(cmd, cwd=None):
    print(f"\n>>> {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def step1_fetch_binaries():
    print("=== Step 1: Fetch binaries ===")
    run([sys.executable, str(ROOT / "scripts" / "fetch_binaries.py")])


def step2_build_python():
    print("=== Step 2: Build Python backend with PyInstaller ===")
    run([sys.executable, "-m", "pip", "install", "pyinstaller"])
    run([sys.executable, str(ROOT / "scripts" / "build.py")])


def step3_build_electron():
    print("=== Step 3: Build Electron app ===")
    desktop = ROOT / "desktop"
    run(["npm", "install"], cwd=desktop)
    run(["npm", "run", "build"], cwd=desktop)
    run(["npm", "run", "electron:build"], cwd=desktop)


def main():
    step1_fetch_binaries()
    step2_build_python()
    step3_build_electron()
    print("\n=== All done! ===")
    print(f"Output: {ROOT / 'desktop' / 'dist-electron'}")


if __name__ == "__main__":
    main()
