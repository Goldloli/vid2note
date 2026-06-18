"""FastAPI 入口"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from vid2note_core.errors import Vid2NoteError
from vid2note_core.worker import get_worker

from vid2note_server.api import artifacts, config, events, logs, models, process, tasks, upload


@asynccontextmanager
async def lifespan(app: FastAPI):
    worker = get_worker()
    await worker.start()
    yield
    await worker.stop()


app = FastAPI(title="vid2note", version="0.1.0", lifespan=lifespan)

# CORS：桌面端用 file:// 加载（origin 为 null），本地开发为 localhost:5173。
# 不再 allow_origins=["*"] + allow_credentials=True（安全 bug）。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["null", "http://localhost:5173", "app://"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


@app.exception_handler(Vid2NoteError)
async def vid2note_error_handler(request: Request, exc: Vid2NoteError):
    """把 Vid2NoteError 翻译为结构化 HTTP 响应（不再泄漏 500 + 堆栈）。

    retryable 错误（限流、超时、临时网络）→ 503 Service Unavailable
    非重试错误（配置错误、密钥缺失）→ 400 Bad Request
    """
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


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """枚举/参数校验错误 → 422 Unprocessable Entity。"""
    return JSONResponse(
        status_code=422,
        content={"error": "VALIDATION_ERROR", "message": str(exc)},
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

    DB 不可用时返回 503（不再返回 200 degraded，避免 healthcheck 误判健康）。
    """
    from vid2note_core.storage.task_repo import TaskRepository

    try:
        repo = TaskRepository()
        active = repo.count_active()
        return {"status": "ok", "active_tasks": active}
    except Exception as e:  # noqa: BLE001
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "error": str(e)},
        )
