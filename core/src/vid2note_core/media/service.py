from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel

from vid2note_core.audio.ffmpeg_binary import get_ffmpeg
from vid2note_core.errors import Vid2NoteError
from vid2note_core.source.identity import SourceIdentityRepository
from vid2note_core.source.models import SourceRecord
from vid2note_core.vault.layout import VaultLayout

CODEC_VERSION = "v1"
_SOURCE_ID = re.compile(r"^src_\d{8}_[0-9a-f]{8}$")


class MediaRangeError(Vid2NoteError):
    def __init__(self, message: str):
        super().__init__(
            message,
            code="MEDIA_RANGE_INVALID",
            user_message="媒体时间范围无效",
            step="media",
        )


class SourceMediaUnavailableError(Vid2NoteError):
    def __init__(self, source: SourceRecord):
        super().__init__(
            f"Original media is unavailable for {source.source_id}",
            code="SOURCE_MEDIA_UNAVAILABLE",
            user_message="原始媒体不可用，可继续查看转录文本",
            step="media",
        )
        self.details = {
            "transcript_path": f"raw/{source.source_id}/transcript.md",
            "canonical_url": source.canonical_url,
        }


class MediaReference(BaseModel):
    source_id: str
    kind: Literal["frame", "clip", "audio"]
    start_ms: int
    end_ms: int | None = None
    rendered_start_ms: int
    rendered_end_ms: int | None = None
    asset_path: str
    cached: bool
    playable: bool


class CommandRunner(Protocol):
    def run(self, command: list[str]) -> None: ...


class FFmpegRunner:
    def run(self, command: list[str]) -> None:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            raise Vid2NoteError(
                f"ffmpeg failed: {result.stderr}",
                code="MEDIA_RENDER_FAILED",
                user_message="媒体证据生成失败",
                step="media",
            )


def cache_key(
    content_sha256: str,
    kind: str,
    start_ms: int,
    end_ms: int | None,
    buffer_ms: int,
) -> str:
    material = f"{content_sha256}|{kind}|{start_ms}|{end_ms}|{buffer_ms}|{CODEC_VERSION}"
    return hashlib.sha256(material.encode()).hexdigest()


class MediaService:
    def __init__(
        self,
        layout: VaultLayout,
        *,
        runner: CommandRunner | None = None,
        ffmpeg: str | Path | None = None,
    ):
        self.layout = layout
        self.identities = SourceIdentityRepository(layout.root)
        self.runner = runner or FFmpegRunner()
        self.ffmpeg = str(ffmpeg or get_ffmpeg())

    def frame(self, source_id: str, *, timestamp_ms: int) -> MediaReference:
        source, original = self._source_media(source_id)
        if timestamp_ms < 0 or timestamp_ms > source.duration_ms:
            raise MediaRangeError("timestamp_ms must be within source duration")
        key = cache_key(source.content_sha256, "frame", timestamp_ms, None, 0)
        output = self.layout.private / "cache" / "frames" / f"{key}.jpg"
        cached = output.is_file()
        if not cached:
            self._render_atomic(
                [
                    self.ffmpeg,
                    "-ss",
                    _seconds(timestamp_ms),
                    "-i",
                    str(original),
                    "-frames:v",
                    "1",
                    "-q:v",
                    "2",
                    "-y",
                    "",
                ],
                output,
            )
        return MediaReference(
            source_id=source_id,
            kind="frame",
            start_ms=timestamp_ms,
            rendered_start_ms=timestamp_ms,
            asset_path=output.relative_to(self.layout.root).as_posix(),
            cached=cached,
            playable=True,
        )

    def clip(
        self,
        source_id: str,
        *,
        start_ms: int,
        end_ms: int,
        buffer_ms: int = 1500,
    ) -> MediaReference:
        source, original = self._source_media(source_id)
        if start_ms < 0 or end_ms <= start_ms or end_ms > source.duration_ms or buffer_ms < 0:
            raise MediaRangeError("clip range must be ordered and within source duration")
        rendered_start = max(0, start_ms - buffer_ms)
        rendered_end = min(source.duration_ms, end_ms + buffer_ms)
        key = cache_key(source.content_sha256, "clip", start_ms, end_ms, buffer_ms)
        output = self.layout.private / "cache" / "clips" / f"{key}.mp4"
        cached = output.is_file()
        if not cached:
            self._render_atomic(
                [
                    self.ffmpeg,
                    "-ss",
                    _seconds(rendered_start),
                    "-i",
                    str(original),
                    "-t",
                    _seconds(rendered_end - rendered_start),
                    "-c:v",
                    "libx264",
                    "-c:a",
                    "aac",
                    "-movflags",
                    "+faststart",
                    "-y",
                    "",
                ],
                output,
            )
        return MediaReference(
            source_id=source_id,
            kind="clip",
            start_ms=start_ms,
            end_ms=end_ms,
            rendered_start_ms=rendered_start,
            rendered_end_ms=rendered_end,
            asset_path=output.relative_to(self.layout.root).as_posix(),
            cached=cached,
            playable=True,
        )

    def promote(self, reference: MediaReference) -> MediaReference:
        if not _SOURCE_ID.fullmatch(reference.source_id):
            raise MediaRangeError("source_id is invalid")
        source = (self.layout.root / reference.asset_path).resolve()
        cache_root = (self.layout.private / "cache").resolve()
        if not source.is_file() or not source.is_relative_to(cache_root):
            raise MediaRangeError("only generated cache assets can be promoted")
        destination_dir = self.layout.assets / reference.source_id
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / source.name
        descriptor, temporary_name = tempfile.mkstemp(dir=destination_dir, prefix=".promote-")
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            shutil.copyfile(source, temporary)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return reference.model_copy(
            update={"asset_path": destination.relative_to(self.layout.root).as_posix()}
        )

    def _source_media(self, source_id: str) -> tuple[SourceRecord, Path]:
        if not _SOURCE_ID.fullmatch(source_id):
            raise SourceMediaUnavailableError(_missing_source(source_id))
        source = self.identities.get(source_id)
        if source is None:
            raise SourceMediaUnavailableError(_missing_source(source_id))
        if not source.original_available or source.original_relative_path is None:
            raise SourceMediaUnavailableError(source)
        original = (self.layout.root / source.original_relative_path).resolve()
        allowed = (self.layout.raw / source.source_id).resolve()
        if not original.is_file() or not original.is_relative_to(allowed):
            raise SourceMediaUnavailableError(source)
        return source, original

    @staticmethod
    def _require_output(output: Path) -> None:
        if not output.is_file() or output.stat().st_size == 0:
            raise Vid2NoteError(
                "ffmpeg did not create media output",
                code="MEDIA_RENDER_FAILED",
                user_message="媒体证据生成失败",
                step="media",
            )

    def _render_atomic(self, command: list[str], output: Path) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=output.parent,
            prefix=f".{output.stem}-",
            suffix=output.suffix,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        temporary.unlink()
        command[-1] = str(temporary)
        try:
            self.runner.run(command)
            self._require_output(temporary)
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)


def _seconds(milliseconds: int) -> str:
    return f"{milliseconds / 1000:.3f}"


def _missing_source(source_id: str) -> SourceRecord:
    from datetime import UTC, datetime

    return SourceRecord(
        source_id=source_id,
        canonical_url=None,
        content_sha256="",
        title="",
        duration_ms=0,
        imported_at=datetime.now(UTC),
        original_available=False,
        original_relative_path=None,
    )
