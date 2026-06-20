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
from hashlib import sha256
from pathlib import Path

BIN_DIR = Path(__file__).parent / "bin"
OS = platform.system().lower()
ARCH = platform.machine().lower()
FFMPEG_MACOS_URL = "https://evermeet.cx/ffmpeg/ffmpeg-8.1.2.zip"
FFMPEG_MACOS_SHA256 = "60725ea0467ccaf900bf294d3567c302a802dc661f03bdde6aa7ecc9ccf05c4f"
YTDLP_MACOS_URL = "https://github.com/yt-dlp/yt-dlp/releases/download/2026.06.09/yt-dlp_macos"
YTDLP_MACOS_SHA256 = "b82c3626952e6c14eaf654cc565866775ffd0b9ffb7021628ac59b42c2f4f244"
YTDLP_LINUX_URL = "https://github.com/yt-dlp/yt-dlp/releases/download/2026.06.09/yt-dlp"
YTDLP_LINUX_SHA256 = "e5d57466682cfa9d61e9cf7c8a4f09b00f4a62af37d3bbdc4bcffdf63615feac"


def ensure_bin_dir():
    BIN_DIR.mkdir(parents=True, exist_ok=True)


def download(url: str, dest: Path):
    print(f"Downloading {url} -> {dest}")
    urllib.request.urlretrieve(url, dest)
    print(f"  Saved {dest.stat().st_size} bytes")


def make_executable(path: Path):
    st = os.stat(path)
    os.chmod(path, st.st_mode | stat.S_IEXEC)


def verify_sha256(path: Path, expected: str) -> None:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected:
        path.unlink(missing_ok=True)
        raise RuntimeError(f"binary checksum mismatch for {path.name}")


def verify_package_binaries() -> None:
    if OS != "darwin":
        raise RuntimeError("standalone Electron packaging currently supports macOS only")
    verify_sha256(BIN_DIR / "ffmpeg", FFMPEG_MACOS_SHA256)
    verify_sha256(BIN_DIR / "yt-dlp", YTDLP_MACOS_SHA256)


def fetch_ffmpeg():
    """下载 ffmpeg 静态构建"""
    ensure_bin_dir()
    dest = BIN_DIR / "ffmpeg"
    if dest.exists():
        print("ffmpeg already exists, skipping")
        return

    if OS == "darwin":
        # macOS arm64/x64 通用构建
        url = FFMPEG_MACOS_URL
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
        url = YTDLP_MACOS_URL
        expected_sha256 = YTDLP_MACOS_SHA256
    elif OS == "linux":
        url = YTDLP_LINUX_URL
        expected_sha256 = YTDLP_LINUX_SHA256
    else:
        print("Windows not yet supported in this script")
        sys.exit(1)

    download(url, dest)
    verify_sha256(dest, expected_sha256)
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
