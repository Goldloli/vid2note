#!/usr/bin/env python3
"""
自动下载 vid2note 所需的二进制工具：ffmpeg, yt-dlp, BBDown, you-get
"""

import os
import platform
import stat
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

BIN_DIR = Path(__file__).parent / "bin"
OS = platform.system().lower()
ARCH = platform.machine().lower()


def ensure_bin_dir():
    BIN_DIR.mkdir(parents=True, exist_ok=True)


def download(url: str, dest: Path):
    print(f"Downloading {url} -> {dest}")
    urllib.request.urlretrieve(url, dest)
    print(f"  Saved {dest.stat().st_size} bytes")


def make_executable(path: Path):
    st = os.stat(path)
    os.chmod(path, st.st_mode | stat.S_IEXEC)


def fetch_ffmpeg():
    """下载 ffmpeg 静态构建"""
    ensure_bin_dir()
    dest = BIN_DIR / "ffmpeg"
    if dest.exists():
        print("ffmpeg already exists, skipping")
        return

    if OS == "darwin":
        # macOS arm64/x64 通用构建
        url = "https://evermeet.cx/ffmpeg/getrelease/zip"
        tmp = BIN_DIR / "ffmpeg.zip"
        download(url, tmp)
        with zipfile.ZipFile(tmp, "r") as z:
            z.extractall(BIN_DIR)
        tmp.unlink()
    elif OS == "linux":
        # Linux x64 静态构建
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        tmp = BIN_DIR / "ffmpeg.tar.xz"
        download(url, tmp)
        with tarfile.open(tmp, "r:xz") as tar:
            # 提取第一个包含 ffmpeg 可执行文件的内容
            for member in tar.getmembers():
                if member.name.endswith("/ffmpeg"):
                    member.name = "ffmpeg"
                    tar.extract(member, BIN_DIR)
                    break
        tmp.unlink()
    else:
        print("Windows not yet supported in this script, please install ffmpeg manually")
        sys.exit(1)

    make_executable(dest)
    print("ffmpeg ready")


def fetch_ytdlp():
    """下载 yt-dlp"""
    ensure_bin_dir()
    dest = BIN_DIR / "yt-dlp"
    if dest.exists():
        print("yt-dlp already exists, skipping")
        return

    if OS == "darwin":
        url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos"
    elif OS == "linux":
        url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
    else:
        print("Windows not yet supported in this script")
        sys.exit(1)

    download(url, dest)
    make_executable(dest)
    print("yt-dlp ready")


def fetch_bbdown():
    """下载 BBDown (Bilibili 下载器)

    BBDown release 用版本化的 zip 命名（如 BBDown_1.6.3_20240814_osx-arm64.zip），
    而非固定的 latest/download 路径，故通过 GitHub API 解析最新 asset。
    """
    import json as _json

    ensure_bin_dir()
    dest = BIN_DIR / "BBDown"
    if dest.exists():
        print("BBDown already exists, skipping")
        return

    if OS == "darwin":
        arch_kw = "arm64" if ARCH == "arm64" else "x64"
        platform_kw = "osx"
    elif OS == "linux":
        arch_kw = "x64"
        platform_kw = "linux"
    else:
        print("Windows not yet supported in this script")
        sys.exit(1)

    # 通过 API 找最新 release 中匹配平台的 asset
    api_url = "https://api.github.com/repos/nilaoda/BBDown/releases/latest"
    try:
        req = urllib.request.Request(api_url, headers={"Accept": "application/vnd.github+json"})
        data = _json.loads(urllib.request.urlopen(req, timeout=30).read())
    except Exception as e:  # noqa: BLE001
        print(f"无法查询 BBDown 最新版本: {e}")
        return

    asset_url = None
    for a in data.get("assets", []):
        name = a["name"].lower()
        if platform_kw in name and arch_kw in name and name.endswith(".zip"):
            asset_url = a["browser_download_url"]
            break
    if not asset_url:
        print(f"未找到 BBDown {platform_kw}-{arch_kw} asset，跳过（yt-dlp 可兜底）")
        return

    # 下载 zip 并解压出 BBDown 可执行文件
    tmp = BIN_DIR / "BBDown.zip"
    download(asset_url, tmp)
    with zipfile.ZipFile(tmp, "r") as z:
        # 找到 zip 内的 BBDown 可执行文件
        for member in z.namelist():
            base = member.split("/")[-1]
            if base == "BBDown" or (base.startswith("BBDown") and "." not in base):
                # 提取并改名为 BBDown
                member_data = z.read(member)
                dest.write_bytes(member_data)
                break
    tmp.unlink(missing_ok=True)
    make_executable(dest)
    print("BBDown ready")


def fetch_you_get():
    """you-get 通过 pip 安装，不需要单独下载二进制"""
    print("you-get is installed via pip, skipping binary download")


def main():
    print(f"OS: {OS}, ARCH: {ARCH}")
    print(f"Binary directory: {BIN_DIR}")
    fetch_ffmpeg()
    fetch_ytdlp()
    fetch_bbdown()
    fetch_you_get()
    print("All binaries ready!")


if __name__ == "__main__":
    main()
