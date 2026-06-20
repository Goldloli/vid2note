from pydantic import BaseModel, Field
from vid2note_core.wiki.models import ChangeOperation, ChangeSet, Contradiction
from vid2note_core.wiki.policy import AutonomyMode


class ApproveChangeSetRequest(BaseModel):
    operation_indexes: list[int] | None = None


class RejectChangeSetRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class ReviseChangeSetRequest(BaseModel):
    summary: str = Field(min_length=1)
    operations: list[ChangeOperation] = Field(min_length=1)
    contradictions: list[Contradiction] = []
    agent_runtime: str | None = None


class AutonomyModeRequest(BaseModel):
    mode: AutonomyMode


class AutonomyModeResponse(BaseModel):
    mode: AutonomyMode


__all__ = [
    "ApproveChangeSetRequest",
    "AutonomyModeRequest",
    "AutonomyModeResponse",
    "ChangeSet",
    "RejectChangeSetRequest",
    "ReviseChangeSetRequest",
]
