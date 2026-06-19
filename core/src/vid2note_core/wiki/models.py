from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_CHANGESET_ID = re.compile(r"^chg_[a-f0-9]{12}$")


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class Citation(FrozenModel):
    source_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> Citation:
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self


class Contradiction(FrozenModel):
    topic: str
    claim_a: str
    claim_b: str
    citations_a: list[Citation] = Field(min_length=1)
    citations_b: list[Citation] = Field(min_length=1)
    requires_approval: bool = True


class ValidationIssue(FrozenModel):
    code: str
    severity: Literal["error", "warning"]
    operation_index: int | None = None
    path: str | None = None
    message: str


class ValidationResult(FrozenModel):
    valid: bool
    issues: list[ValidationIssue]


class ChangeOperation(FrozenModel):
    page_id: str
    path: str
    base_hash: str | None = None
    action: Literal["create", "update", "rename"]
    before: str | None = None
    after: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    citations: list[Citation]


class ChangeSet(FrozenModel):
    id: str
    created_at: datetime
    source_ids: list[str] = Field(min_length=1)
    base_revision: str
    agent_runtime: str
    summary: str = Field(min_length=1)
    operations: list[ChangeOperation] = Field(min_length=1)
    contradictions: list[Contradiction]
    validation_result: ValidationResult | None = None
    status: Literal["pending", "applied", "rejected", "reverted"] = "pending"
    supersedes: str | None = None
    parent_id: str | None = None
    rejection_reason: str | None = None

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not _CHANGESET_ID.fullmatch(value):
            raise ValueError("invalid ChangeSet id")
        return value
