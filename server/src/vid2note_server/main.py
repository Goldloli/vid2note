"""FastAPI entry point."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from vid2note_core.errors import Vid2NoteError
from vid2note_core.paths import RuntimePaths

from vid2note_server.api import artifacts, config, events, logs, models, process, tasks, upload
from vid2note_server.dependencies import ServicesDependency, build_services


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
        await services.worker.start()
        try:
            yield
        finally:
            await services.worker.stop()
            services.database.close_all_connections()

    application = FastAPI(title="vid2note", version="0.1.0", lifespan=lifespan)
    application.state.services = services
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["null", "http://localhost:5173", "app://"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    @application.exception_handler(Vid2NoteError)
    async def vid2note_error_handler(request: Request, exc: Vid2NoteError):
        status = 503 if exc.retryable else 400
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": exc.code,
                    "message": str(exc),
                    "retryable": exc.retryable,
                    "step": exc.step,
                },
                "message": exc.user_message or str(exc),
            },
        )

    @application.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(
            status_code=422,
            content={"error": "VALIDATION_ERROR", "message": str(exc)},
        )

    application.include_router(tasks.router, prefix="/api/v1")
    application.include_router(process.router, prefix="/api/v1")
    application.include_router(upload.router, prefix="/api/v1")
    application.include_router(config.router, prefix="/api/v1")
    application.include_router(models.router, prefix="/api/v1")
    application.include_router(events.router, prefix="/api/v1")
    application.include_router(logs.router, prefix="/api/v1")
    application.include_router(artifacts.router, prefix="/api/v1")

    @application.get("/health")
    @application.get("/api/v1/health")
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
