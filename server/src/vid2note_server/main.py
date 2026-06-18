"""FastAPI 入口"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from vid2note_core.worker import get_worker

from vid2note_server.api import artifacts, config, events, logs, models, process, tasks, upload


@asynccontextmanager
async def lifespan(app: FastAPI):
    worker = get_worker()
    await worker.start()
    yield
    await worker.stop()


app = FastAPI(title="vid2note", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router, prefix="/api/v1")
app.include_router(process.router, prefix="/api/v1")
app.include_router(upload.router, prefix="/api/v1")
app.include_router(config.router, prefix="/api/v1")
app.include_router(models.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")
app.include_router(logs.router, prefix="/api/v1")
app.include_router(artifacts.router, prefix="/api/v1")


@app.get("/health")
@app.get("/api/v1/health")
async def health():
    """健康检查。

    同时挂在 /health 和 /api/v1/health：
    - /api/v1/health 是 Dockerfile healthcheck 和 Electron 主进程 waitForBackend 使用的路径
    - /health 保留向后兼容
    """
    from vid2note_core.storage.task_repo import TaskRepository

    try:
        repo = TaskRepository()
        active = repo.count_active()
        return {"status": "ok", "active_tasks": active}
    except Exception as e:  # noqa: BLE001
        return {"status": "degraded", "error": str(e)}
