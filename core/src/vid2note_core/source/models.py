from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class TimelineSegment(BaseModel):
    segment_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    speaker: str | None = None

    @model_validator(mode="after")
    def validate_range(self) -> TimelineSegment:
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self


class SourceRecord(BaseModel):
    source_id: str
    canonical_url: str | None
    content_sha256: str
    title: str
    duration_ms: int = Field(ge=0)
    imported_at: datetime
    original_available: bool
    original_relative_path: str | None
