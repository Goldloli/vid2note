from fastapi import APIRouter, Query

from vid2note_server.dependencies import ServicesDependency
from vid2note_server.schemas.common import ERROR_RESPONSES
from vid2note_server.schemas.media import MediaReference

router = APIRouter(prefix="/media", tags=["media"], responses=ERROR_RESPONSES)


@router.get("/frame", response_model=MediaReference)
def media_frame(
    source_id: str,
    services: ServicesDependency,
    timestamp_ms: int = Query(ge=0),
):
    return services.media.frame(source_id, timestamp_ms=timestamp_ms)


@router.get("/clip", response_model=MediaReference)
def media_clip(
    source_id: str,
    services: ServicesDependency,
    start_ms: int = Query(ge=0),
    end_ms: int = Query(gt=0),
    buffer_ms: int = Query(default=1500, ge=0, le=30_000),
):
    return services.media.clip(
        source_id,
        start_ms=start_ms,
        end_ms=end_ms,
        buffer_ms=buffer_ms,
    )
