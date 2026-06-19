from datetime import datetime

from pydantic import BaseModel, Field
from vid2note_core.source.models import SourceRecord
from vid2note_core.vault.models import (
    HumanPageUpdate,
    VaultPage,
    VaultSearchResult,
    VaultTreeEntry,
)


class SourceIngestRequest(BaseModel):
    canonical_url: str | None = None
    title: str = Field(min_length=1, max_length=500)
    srt_content: str = Field(min_length=1, max_length=20_000_000)
    note_content: str = Field(min_length=1, max_length=20_000_000)
    imported_at: datetime | None = None


__all__ = [
    "HumanPageUpdate",
    "SourceIngestRequest",
    "SourceRecord",
    "VaultPage",
    "VaultSearchResult",
    "VaultTreeEntry",
]
