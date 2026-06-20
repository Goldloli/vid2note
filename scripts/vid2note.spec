# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for vid2note server.
Builds a standalone directory with all Python dependencies.

外部二进制（ffmpeg/yt-dlp/BBDown）由 scripts/fetch_binaries.py 拉到 scripts/bin/，
这里在打包时把它们收集进产物的 bin/ 子目录；运行时由 BinaryManager 解析。
"""

from PyInstaller.building.build_main import COLLECT, EXE, PYZ, Analysis
from pathlib import Path

# SPECPATH 是 spec 文件所在目录（<repo>/scripts），其 parent 即仓库根
ROOT = Path(SPECPATH).parent
BIN_DIR = ROOT / "scripts" / "bin"

# 收集已拉取的外部二进制（仅收集存在的，避免打包前未 fetch 就失败）
_binaries = []
for name in ("ffmpeg", "yt-dlp", "BBDown"):
    p = BIN_DIR / name
    if p.exists():
        _binaries.append((str(p), "bin"))

a = Analysis(
    [str(ROOT / "server" / "src" / "vid2note_server" / "entrypoint.py")],
    pathex=[
        str(ROOT / "core" / "src"),
        str(ROOT / "server" / "src"),
    ],
    binaries=_binaries,
    datas=[
        (str(ROOT / "core" / "src" / "vid2note_core"), "vid2note_core"),
        (str(ROOT / "server" / "src" / "vid2note_server"), "vid2note_server"),
    ],
    hiddenimports=[
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "fastapi",
        "pydantic",
        "pydantic_settings",
        "yaml",
        "openai",
        "httpx",
        "fitz",
        "PIL",
        "aiofiles",
        "slowapi",
        "starlette",
        "python_multipart",
        # pkg_resources 的冻结运行时 hook 在 Python 3.11 会通过 setuptools
        # vendor importer 加载 backports.tarfile；显式收集以保留该别名。
        "setuptools._vendor.backports",
        "setuptools._vendor.backports.tarfile",
        # 本地 ASR（可选；缺失时 _default_asr 会回退）
        "funasr",
        "torch",
        "torchaudio",
        "modelscope",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy.tests",
        "scipy",
        "pandas",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="vid2note-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="vid2note",
    # 输出目录由 build.py 的 --distpath 控制（指向 python-dist）
)
