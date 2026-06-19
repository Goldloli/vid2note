from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse

from vid2note_server.dependencies import ServicesDependency
from vid2note_server.schemas.agents import (
    AgentMessageRequest,
    AgentRunResponse,
    AgentSessionResponse,
    CreateAgentSessionRequest,
    RuntimeResponse,
)
from vid2note_server.schemas.common import ERROR_RESPONSES

router = APIRouter(tags=["agents"], responses=ERROR_RESPONSES)


@router.get("/agents", response_model=list[RuntimeResponse])
async def list_agents(services: ServicesDependency):
    results = []
    for runtime_id, descriptor in services.agent_registry.descriptors.items():
        runtime = services.agent_sessions.runtimes[runtime_id]
        results.append(
            RuntimeResponse(
                id=runtime_id,
                label=descriptor.label,
                detection=await runtime.detect(),
                capabilities=runtime.capabilities(),
            )
        )
    return results


@router.post("/agent/sessions", response_model=AgentSessionResponse, status_code=201)
async def create_session(request: CreateAgentSessionRequest, services: ServicesDependency):
    try:
        runtime = services.agent_sessions.runtimes[request.runtime_id]
        detection = await runtime.detect()
        if not detection.available:
            raise HTTPException(409, detection.reason or "Agent Runtime 不可用")
        return services.agent_sessions.create_session(
            request.runtime_id,
            context_paths=request.context_paths,
            model=request.model,
        )
    except KeyError as exc:
        raise HTTPException(404, "Agent Runtime 不存在或不可用") from exc


@router.get("/agent/sessions", response_model=list[AgentSessionResponse])
async def list_sessions(services: ServicesDependency):
    return services.agent_sessions.list_sessions()


@router.get("/agent/sessions/{session_id}", response_model=AgentSessionResponse)
async def get_session(session_id: str, services: ServicesDependency):
    session = services.agent_sessions.get_session(session_id)
    if session is None:
        raise HTTPException(404, "Agent Session 不存在")
    return session


@router.post(
    "/agent/sessions/{session_id}/messages",
    response_model=AgentRunResponse,
    status_code=202,
)
async def send_message(
    session_id: str,
    request: AgentMessageRequest,
    services: ServicesDependency,
):
    try:
        return services.agent_sessions.send_message(session_id, request.message)
    except KeyError as exc:
        raise HTTPException(404, "Agent Session 不存在") from exc


async def _session_events(session_id: str, services, after: int):
    history = services.agent_sessions.list_events(session_id)
    for event in history[after:]:
        yield f"data: {event.model_dump_json()}\n\n"
    session = services.agent_sessions.get_session(session_id)
    if session is not None and session.status in {"completed", "failed", "cancelled"}:
        return
    queue = services.agent_sessions.subscribe(session_id)
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30)
            except TimeoutError:
                yield ":keep-alive\n\n"
                continue
            yield f"data: {event.model_dump_json()}\n\n"
            if event.type in {"run.completed", "run.failed", "run.cancelled"}:
                return
    finally:
        services.agent_sessions.unsubscribe(session_id, queue)


@router.get("/agent/sessions/{session_id}/events")
async def session_events(
    session_id: str,
    services: ServicesDependency,
    after: int = Query(default=0, ge=0),
):
    if services.agent_sessions.get_session(session_id) is None:
        raise HTTPException(404, "Agent Session 不存在")
    return StreamingResponse(
        _session_events(session_id, services, after),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/agent/runs/{run_id}/cancel", status_code=204)
async def cancel_run(run_id: str, services: ServicesDependency):
    try:
        await services.agent_sessions.cancel(run_id)
    except KeyError as exc:
        raise HTTPException(404, "Agent Run 不存在") from exc
    return Response(status_code=204)
