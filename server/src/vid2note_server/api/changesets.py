from datetime import UTC, datetime
from secrets import token_hex
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from vid2note_core.wiki.models import ChangeSet

from vid2note_server.dependencies import Services, ServicesDependency
from vid2note_server.schemas.changesets import (
    ApproveChangeSetRequest,
    RejectChangeSetRequest,
    ReviseChangeSetRequest,
)
from vid2note_server.schemas.common import ERROR_RESPONSES

router = APIRouter(prefix="/changesets", tags=["changesets"], responses=ERROR_RESPONSES)


@router.get("", response_model=list[ChangeSet])
async def list_changesets(
    services: ServicesDependency,
    status: Literal["pending", "applied", "rejected"] = Query(default="pending"),
):
    return services.changesets.list(status)


@router.get("/{changeset_id}", response_model=ChangeSet)
async def get_changeset(changeset_id: str, services: ServicesDependency):
    changeset = _get(changeset_id, services)
    return changeset


@router.post("/{changeset_id}/approve", response_model=ChangeSet)
async def approve_changeset(
    changeset_id: str,
    request: ApproveChangeSetRequest,
    services: ServicesDependency,
):
    original = _pending(changeset_id, services)
    selected = request.operation_indexes
    candidate = original
    if selected is not None:
        indexes = sorted(set(selected))
        if not indexes or indexes[0] < 0 or indexes[-1] >= len(original.operations):
            raise HTTPException(422, "批准的 operation index 无效")
        if indexes != list(range(len(original.operations))):
            candidate = original.model_copy(
                update={
                    "id": f"chg_{token_hex(6)}",
                    "created_at": datetime.now(UTC),
                    "base_revision": original.id,
                    "summary": f"Partial approval of {original.id}",
                    "operations": [original.operations[index] for index in indexes],
                    "parent_id": original.id,
                }
            )
            services.changesets.save_pending(candidate)
    return services.applier.apply(candidate)


@router.post("/{changeset_id}/reject", response_model=ChangeSet)
async def reject_changeset(
    changeset_id: str,
    request: RejectChangeSetRequest,
    services: ServicesDependency,
):
    _pending(changeset_id, services)
    return services.changesets.reject(changeset_id, reason=request.reason)


@router.post("/{changeset_id}/revert", response_model=ChangeSet)
async def revert_changeset(changeset_id: str, services: ServicesDependency):
    try:
        return services.applier.revert(changeset_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{changeset_id}/revise", response_model=ChangeSet)
async def revise_changeset(
    changeset_id: str,
    request: ReviseChangeSetRequest,
    services: ServicesDependency,
):
    original = _pending(changeset_id, services)
    revised = ChangeSet(
        id=f"chg_{token_hex(6)}",
        created_at=datetime.now(UTC),
        source_ids=original.source_ids,
        base_revision=original.base_revision,
        agent_runtime=request.agent_runtime or original.agent_runtime,
        summary=request.summary,
        operations=request.operations,
        contradictions=request.contradictions,
        supersedes=original.id,
    )
    services.changesets.save_pending(revised)
    services.changesets.reject(original.id, reason=f"superseded by {revised.id}")
    return revised


def _get(changeset_id: str, services: Services) -> ChangeSet:
    try:
        changeset = services.changesets.get(changeset_id)
    except ValueError as exc:
        raise HTTPException(404, "ChangeSet 不存在") from exc
    if changeset is None:
        raise HTTPException(404, "ChangeSet 不存在")
    return changeset


def _pending(changeset_id: str, services: Services) -> ChangeSet:
    changeset = _get(changeset_id, services)
    if changeset.status != "pending":
        raise HTTPException(409, f"ChangeSet 状态为 {changeset.status}")
    return changeset
