from __future__ import annotations

import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from vid2note_core.source.registrar import SourceRegistration

from vid2note_server.dependencies import ServicesDependency
from vid2note_server.schemas.common import ERROR_RESPONSES
from vid2note_server.schemas.vault import SourceIngestRequest, SourceRecord

router = APIRouter(prefix="/sources", tags=["sources"], responses=ERROR_RESPONSES)
_SOURCE_ID = re.compile(r"^src_\d{8}_[0-9a-f]{8}$")


@router.post("/ingest", response_model=SourceRecord)
async def ingest_source(request: SourceIngestRequest, services: ServicesDependency):
    staging = Path(
        tempfile.mkdtemp(prefix="api-ingest-", dir=services.vault_layout.private / "staging")
    )
    try:
        srt_path = staging / "transcript.srt"
        note_path = staging / "note.md"
        srt_path.write_text(request.srt_content, encoding="utf-8")
        note_path.write_text(request.note_content, encoding="utf-8")
        return services.source_registrar.register(
            SourceRegistration(
                task_id=f"ingest_{uuid4().hex}",
                canonical_url=request.canonical_url,
                title=request.title,
                imported_at=request.imported_at or datetime.now(UTC),
                srt_path=srt_path,
                note_path=note_path,
            )
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)


@router.get("/{source_id}", response_model=SourceRecord)
async def get_source(source_id: str, services: ServicesDependency):
    if not _SOURCE_ID.fullmatch(source_id):
        raise HTTPException(404, "来源不存在")
    source = services.source_registrar.identities.get(source_id)
    if source is None:
        raise HTTPException(404, "来源不存在")
    return source
