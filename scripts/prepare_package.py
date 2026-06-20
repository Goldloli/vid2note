"""Build the self-contained backend consumed by electron-builder."""

from fetch_binaries import BIN_DIR, fetch_ffmpeg, fetch_ytdlp, verify_package_binaries

from build import build


def main() -> None:
    if not (BIN_DIR / "ffmpeg").is_file():
        fetch_ffmpeg()
    if not (BIN_DIR / "yt-dlp").is_file():
        fetch_ytdlp()
    verify_package_binaries()
    build()


if __name__ == "__main__":
    main()
