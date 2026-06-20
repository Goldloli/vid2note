import hashlib
import importlib.util
from pathlib import Path

import pytest


def _module():
    script = Path(__file__).parents[3] / "scripts" / "fetch_binaries.py"
    spec = importlib.util.spec_from_file_location("fetch_binaries", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_binary_downloads_are_version_pinned_and_checksum_verified(tmp_path):
    module = _module()
    artifact = tmp_path / "artifact"
    artifact.write_bytes(b"pinned binary")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()

    module.verify_sha256(artifact, digest)
    with pytest.raises(RuntimeError, match="checksum"):
        module.verify_sha256(artifact, "0" * 64)

    assert "/download/2026.06.09/" in module.YTDLP_MACOS_URL
    assert "ffmpeg-8.1.2.zip" in module.FFMPEG_MACOS_URL


def test_package_verifies_existing_ffmpeg_and_ytdlp(monkeypatch, tmp_path):
    module = _module()
    monkeypatch.setattr(module, "BIN_DIR", tmp_path)
    monkeypatch.setattr(module, "OS", "darwin")
    (tmp_path / "ffmpeg").write_bytes(b"ffmpeg")
    (tmp_path / "yt-dlp").write_bytes(b"yt-dlp")
    verified = []
    monkeypatch.setattr(
        module,
        "verify_sha256",
        lambda path, expected: verified.append((path.name, expected)),
    )

    module.verify_package_binaries()

    assert verified == [
        ("ffmpeg", module.FFMPEG_MACOS_SHA256),
        ("yt-dlp", module.YTDLP_MACOS_SHA256),
    ]
