"""FastAPI entry point."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from vid2note_core.errors import Vid2NoteError
from vid2note_core.paths import RuntimePaths
from vid2note_core.vault.models import VaultConflict

from vid2note_server.api import (
    agents,
    artifacts,
    changesets,
    config,
    events,
    logs,
    media,
    models,
    process,
    sources,
    tasks,
    upload,
    vault,
    wiki,
)
from vid2note_server.dependencies import ServicesDependency, build_services
from vid2note_server.schemas.common import ErrorEnvelope, ErrorResponse, HealthResponse

logger = logging.getLogger(__name__)


def _default_data_root() -> Path:
    configured = os.environ.get("VID2NOTE_DATA_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "data"


def create_app(data_root: str | Path | None = None) -> FastAPI:
    paths = RuntimePaths.from_data_root(data_root or _default_data_root())
    services = build_services(paths)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.services = services
        await asyncio.to_thread(services.applier.recover_incomplete)
        await services.watcher.start()
        await services.worker.start()
        try:
            yield
        finally:
            await services.agent_sessions.shutdown()
            await services.watcher.stop()
            await services.worker.stop()
            services.database.close_all_connections()

    application = FastAPI(title="vid2note", version="0.1.0", lifespan=lifespan)
    application.state.services = services
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "null",
            "http://localhost:5173",
            "http://localhost:5174",
            "app://",
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    def error_response(status_code: int, envelope: ErrorEnvelope) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content=ErrorResponse(error=envelope).model_dump(mode="json", exclude_none=True),
        )

    @application.exception_handler(VaultConflict)
    async def vault_conflict_handler(request: Request, exc: VaultConflict):
        return error_response(
            409,
            ErrorEnvelope(
                code=exc.code,
                message=str(exc),
                user_message=exc.user_message or str(exc),
                retryable=False,
                component="vault",
                operation=request.url.path,
            ),
        )

    @application.exception_handler(Vid2NoteError)
    async def vid2note_error_handler(request: Request, exc: Vid2NoteError):
        status = 503 if exc.retryable else 400
        return error_response(
            status,
            ErrorEnvelope(
                code=exc.code,
                message=str(exc),
                user_message=exc.user_message or str(exc),
                retryable=exc.retryable,
                component=exc.step or "core",
                operation=request.url.path,
                details=getattr(exc, "details", None),
            ),
        )

    @application.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException):
        message = str(exc.detail)
        return error_response(
            exc.status_code,
            ErrorEnvelope(
                code=f"HTTP_{exc.status_code}",
                message=message,
                user_message=message,
                retryable=False,
                component="api",
                operation=request.url.path,
            ),
        )

    @application.exception_handler(RequestValidationError)
    async def request_validation_error_handler(request: Request, exc: RequestValidationError):
        return error_response(
            422,
            ErrorEnvelope(
                code="VALIDATION_ERROR",
                message="Request validation failed",
                user_message="请求参数无效，请检查输入",
                retryable=False,
                component="api",
                operation=request.url.path,
                details={"errors": jsonable_encoder(exc.errors())},
            ),
        )

    @application.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return error_response(
            422,
            ErrorEnvelope(
                code="VALIDATION_ERROR",
                message=str(exc),
                user_message=str(exc),
                retryable=False,
                component="api",
                operation=request.url.path,
            ),
        )

    @application.exception_handler(Exception)
    async def unknown_error_handler(request: Request, exc: Exception):
        cause_id = uuid4().hex
        logger.exception("Unhandled request error cause_id=%s", cause_id, exc_info=exc)
        return error_response(
            500,
            ErrorEnvelope(
                code="INTERNAL_ERROR",
                message="Internal server error",
                user_message="服务暂时不可用，请稍后重试",
                retryable=False,
                component="server",
                operation=request.url.path,
                cause_id=cause_id,
            ),
        )

    application.include_router(tasks.router, prefix="/api/v1")
    application.include_router(process.router, prefix="/api/v1")
    application.include_router(upload.router, prefix="/api/v1")
    application.include_router(config.router, prefix="/api/v1")
    application.include_router(models.router, prefix="/api/v1")
    application.include_router(events.router, prefix="/api/v1")
    application.include_router(logs.router, prefix="/api/v1")
    application.include_router(artifacts.router, prefix="/api/v1")
    application.include_router(vault.router, prefix="/api/v1")
    application.include_router(sources.router, prefix="/api/v1")
    application.include_router(media.router, prefix="/api/v1")
    application.include_router(changesets.router, prefix="/api/v1")
    application.include_router(wiki.router, prefix="/api/v1")
    application.include_router(agents.router, prefix="/api/v1")

    @application.get("/health", response_model=HealthResponse)
    @application.get("/api/v1/health", response_model=HealthResponse)
    async def health(injected: ServicesDependency):
        try:
            return {"status": "ok", "active_tasks": injected.tasks.count_active()}
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(
                status_code=503,
                content={"status": "degraded", "error": str(exc)},
            )

    return application


app = create_app()
