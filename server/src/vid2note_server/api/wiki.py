from fastapi import APIRouter

from vid2note_server.dependencies import ServicesDependency
from vid2note_server.schemas.changesets import AutonomyModeRequest, AutonomyModeResponse
from vid2note_server.schemas.common import ERROR_RESPONSES

router = APIRouter(prefix="/wiki", tags=["wiki"], responses=ERROR_RESPONSES)


@router.get("/policy", response_model=AutonomyModeResponse)
async def get_wiki_policy(services: ServicesDependency):
    return {"mode": services.config.load().autonomy_mode}


@router.put("/policy", response_model=AutonomyModeResponse)
async def update_wiki_policy(request: AutonomyModeRequest, services: ServicesDependency):
    config = services.config.load()
    config.autonomy_mode = request.mode
    services.config.save(config)
    return {"mode": config.autonomy_mode}
