from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from datetime import UTC, date, datetime, time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml
from pydantic import ValidationError

from vid2note_core.source.models import SourceRecord
from vid2note_core.vault.layout import VaultLayout

logger = logging.getLogger(__name__)

_TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "si"}


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_KEYS
    ]
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "/",
            urlencode(sorted(query)),
            "",
        )
    )


class SourceIdentityRepository:
    def __init__(self, vault_root: str | Path):
        self.layout = VaultLayout.initialize(vault_root)

    def get_or_create(
        self,
        url: str | None,
        content: bytes,
        imported_on: date,
        *,
        title: str = "",
        duration_ms: int = 0,
        original_relative_path: str | None = None,
    ) -> SourceRecord:
        digest = hashlib.sha256(content).hexdigest()
        existing = self.find_by_hash(digest)
        if existing is not None:
            return existing

        source_id = f"src_{imported_on:%Y%m%d}_{digest[:8]}"
        record = SourceRecord(
            source_id=source_id,
            canonical_url=normalize_url(url),
            content_sha256=digest,
            title=title or normalize_url(url) or source_id,
            duration_ms=duration_ms,
            imported_at=datetime.combine(imported_on, time.min, tzinfo=UTC),
            original_available=original_relative_path is not None,
            original_relative_path=original_relative_path,
        )
        self._write_record(record)
        return record

    def find_by_hash(self, digest: str) -> SourceRecord | None:
        for metadata in sorted(self.layout.raw.glob("*/source.yaml")):
            try:
                raw = yaml.safe_load(metadata.read_text(encoding="utf-8"))
                record = SourceRecord.model_validate(raw)
            except (OSError, yaml.YAMLError, ValidationError) as exc:
                logger.warning("Ignoring invalid source metadata %s: %s", metadata, exc)
                continue
            if record.content_sha256 == digest:
                return record
        return None

    def get(self, source_id: str) -> SourceRecord | None:
        metadata = self.layout.raw / source_id / "source.yaml"
        if not metadata.is_file():
            return None
        return SourceRecord.model_validate(yaml.safe_load(metadata.read_text(encoding="utf-8")))

    def _write_record(self, record: SourceRecord) -> None:
        directory = self.layout.raw / record.source_id
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / "source.yaml"
        descriptor, temporary_name = tempfile.mkstemp(
            dir=directory, prefix=".source.", suffix=".tmp"
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                yaml.safe_dump(
                    record.model_dump(mode="json"),
                    output,
                    allow_unicode=True,
                    sort_keys=False,
                )
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
