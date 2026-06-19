from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from vid2note_core.source.identity import SourceIdentityRepository
from vid2note_core.source.models import SourceRecord, TimelineSegment
from vid2note_core.source.transcript import parse_srt, render_transcript
from vid2note_core.utils.security import secure_filename
from vid2note_core.vault.layout import VaultLayout


@dataclass(frozen=True, slots=True)
class SourceRegistration:
    task_id: str
    canonical_url: str | None
    title: str
    imported_at: datetime
    srt_path: Path
    note_path: Path
    original_path: Path | None = None
    duration_ms: int | None = None


class SourceRegistrar:
    def __init__(self, layout: VaultLayout):
        self.layout = layout
        self.identities = SourceIdentityRepository(layout.root)
        self.internal_edit_observer: Callable[[str, str, str], None] | None = None

    def register(self, registration: SourceRegistration) -> SourceRecord:
        self._validate_inputs(registration)
        identity_path = registration.original_path or registration.srt_path
        digest = self._sha256_file(identity_path)
        existing = self.identities.find_by_hash(digest)
        if existing is not None:
            return existing

        srt = registration.srt_path.read_text(encoding="utf-8")
        segments = parse_srt(srt)
        duration_ms = registration.duration_ms or max(
            (segment.end_ms for segment in segments), default=0
        )
        provisional = self.identities.build_record(
            digest,
            registration.canonical_url,
            registration.imported_at.date(),
            title=registration.title,
            duration_ms=duration_ms,
        )
        original_name = self._original_name(registration.original_path)
        record = provisional.model_copy(
            update={
                "original_available": original_name is not None,
                "original_relative_path": (
                    f"raw/{provisional.source_id}/{original_name}" if original_name else None
                ),
            }
        )
        self._stage_and_commit(record, registration, srt, segments, original_name)
        return record

    def _stage_and_commit(
        self,
        record: SourceRecord,
        registration: SourceRegistration,
        srt: str,
        segments: list[TimelineSegment],
        original_name: str | None,
    ) -> None:
        staging = Path(
            tempfile.mkdtemp(prefix=f"{record.source_id}-", dir=self.layout.private / "staging")
        )
        staged_raw = staging / record.source_id
        staged_raw.mkdir()
        note_name = f"{record.source_id}--{self._slug(registration.title)}.md"
        staged_note = staging / note_name
        raw_destination = self.layout.raw / record.source_id
        note_destination = self.layout.sources / note_name
        raw_committed = False
        try:
            self._write_yaml(staged_raw / "source.yaml", record.model_dump(mode="json"))
            (staged_raw / "transcript.srt").write_text(srt, encoding="utf-8")
            (staged_raw / "transcript.md").write_text(
                render_transcript(record.source_id, segments), encoding="utf-8"
            )
            if registration.original_path is not None and original_name is not None:
                shutil.copyfile(registration.original_path, staged_raw / original_name)
            staged_note.write_text(
                self._source_note(record, registration, segments), encoding="utf-8"
            )
            self._validate_staged(staged_raw, staged_note, record)

            os.replace(staged_raw, raw_destination)
            raw_committed = True
            os.replace(staged_note, note_destination)
            if self.internal_edit_observer is not None:
                operation_id = f"source-registration:{registration.task_id}"
                self.internal_edit_observer(
                    (raw_destination / "transcript.md").relative_to(self.layout.root).as_posix(),
                    self._sha256_file(raw_destination / "transcript.md"),
                    operation_id,
                )
                self.internal_edit_observer(
                    note_destination.relative_to(self.layout.root).as_posix(),
                    self._sha256_file(note_destination),
                    operation_id,
                )
        except Exception:
            if raw_committed:
                shutil.rmtree(raw_destination, ignore_errors=True)
            note_destination.unlink(missing_ok=True)
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    @staticmethod
    def _validate_inputs(registration: SourceRegistration) -> None:
        for path in (registration.srt_path, registration.note_path):
            if not path.is_file():
                raise FileNotFoundError(path)
        if registration.original_path is not None and not registration.original_path.is_file():
            raise FileNotFoundError(registration.original_path)

    @staticmethod
    def _validate_staged(raw: Path, note: Path, record: SourceRecord) -> None:
        required = (raw / "source.yaml", raw / "transcript.srt", raw / "transcript.md", note)
        if not all(path.is_file() and path.stat().st_size > 0 for path in required):
            raise ValueError(f"Incomplete staged source: {record.source_id}")

    @staticmethod
    def _source_note(
        record: SourceRecord,
        registration: SourceRegistration,
        segments: list[TimelineSegment],
    ) -> str:
        frontmatter = yaml.safe_dump(
            {
                "source_id": record.source_id,
                "type": "source",
                "title": record.title,
                "canonical_url": record.canonical_url,
                "content_sha256": record.content_sha256,
                "imported_at": record.imported_at.isoformat(),
            },
            allow_unicode=True,
            sort_keys=False,
        ).strip()
        organized = registration.note_path.read_text(encoding="utf-8").strip()
        evidence = [
            (
                f"- [{_time(segment.start_ms)}–{_time(segment.end_ms)}]"
                f"(vid2note://source/{record.source_id}?start={segment.start_ms}"
                f"&end={segment.end_ms}) {segment.text}"
            )
            for segment in segments
        ]
        evidence_text = "\n".join(evidence) or "- 暂无可用时间证据"
        return (
            f"---\n{frontmatter}\n---\n\n# {record.title}\n\n"
            f"## 时间证据\n\n{evidence_text}\n\n"
            f"## 综合/推断\n\n{organized}\n"
        )

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _write_yaml(path: Path, payload: dict[str, object]) -> None:
        with path.open("w", encoding="utf-8") as output:
            yaml.safe_dump(payload, output, allow_unicode=True, sort_keys=False)

    @staticmethod
    def _original_name(path: Path | None) -> str | None:
        if path is None:
            return None
        suffix = path.suffix.lower() or ".bin"
        return f"original{suffix}"

    @staticmethod
    def _slug(title: str) -> str:
        return secure_filename(title.lower().replace(" ", "-"))[:80] or "source"


def _time(milliseconds: int) -> str:
    total_seconds = milliseconds // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
