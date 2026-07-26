"""FastAPI 主应用入口(vid2note v1 · 单容器同源)。

改造点(契约 §4.2 / §0.9):
- 注册 v1 路由(``src.api.v1.v1_router``),**不注册**基底旧 api 路由。
- **移除 CORS 中间件**(单容器同源,前后端同源托管,design D1)。
- 托管前端构建产物(目录不存在时 try 兜底)。
- startup:启动 worker + 启动恢复(残留 running 标 failed)+ 一次 retention 清理扫描。
- shutdown:停止 worker。
"""
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .api.v1 import v1_router
from .config import config_manager
from .utils.logger import error as log_error
from .utils.rate_limiter import limiter

# 服务监听配置(沿用内核 config_manager 的 server 段作为只读默认,契约 §4.2)
_config = config_manager.load()
PORT = _config.server.port
HOST = _config.server.host
DEBUG = _config.server.debug


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期:启动恢复 → 启动 worker → 清理扫描;关闭时停止 worker。"""
    from src.core.kernel import TaskRepository
    from src.retention import run_cleanup_scan
    from src.runtime import start_worker, stop_worker
    from src.runtime.settings import get_settings_snapshot
    from src.runtime.task_service import get_task_service

    svc = get_task_service()
    repo = svc.repo or TaskRepository()
    data_root = svc.data_root

    # 1) 启动恢复:残留 running 任务标 failed(契约 §0.9 / §3.4)
    try:
        n = repo.reset_running_on_startup()
        if n:
            print(f"[startup] 已把 {n} 个中断的运行态任务标记为失败")
    except Exception as exc:  # noqa: BLE001 - 启动恢复失败不阻断服务
        print(f"[startup] 启动恢复失败:{exc}")

    # 2) 启动 worker(消费任务队列)
    print("[startup] 启动任务工作器...")
    await start_worker()
    print("[startup] 任务工作器已启动")

    # 3) 一次 retention 清理扫描(契约 §0.9 / spec storage-retention)
    try:
        report = run_cleanup_scan(repo, data_root, get_settings_snapshot(repo))
        print(f"[startup] 清理扫描完成:释放 {report.freed_bytes} 字节,跳过 {report.skipped_active} 个活跃任务")
    except Exception as exc:  # noqa: BLE001 - 清理失败不阻断服务
        print(f"[startup] 清理扫描失败:{exc}")

    yield

    # 关闭:停止 worker
    print("[shutdown] 正在停止任务工作器...")
    try:
        await stop_worker()
    except Exception as exc:  # noqa: BLE001
        print(f"[shutdown] 停止 worker 失败:{exc}")
    print("[shutdown] 服务已关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title="vid2note",
    description="视频 → Markdown 笔记 + 思维导图(单容器 Web 应用)",
    version="1.0.0",
    lifespan=lifespan,
)

# 速率限制器(v1 路由未挂限速,保留中间件基础以兼容基底工具链)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 注册 v1 路由(prefix /api/v1);不注册基底旧 api 路由(契约 §4.2)
app.include_router(v1_router)


# 根路径 / 由 StaticFiles 托管(返回前端 index.html,design D1 单容器同源);服务信息见 /api/v1/health


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理(中文兜底 500)。"""
    error_detail = traceback.format_exc()
    log_error(f"[API Error] {request.method} {request.url.path}: {exc}\n{error_detail}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": str(exc),
            "message": str(exc),
            "path": request.url.path,
        },
    )


# 托管前端构建产物(单容器同源;目录不存在时跳过,design D1)
try:
    from fastapi.staticfiles import StaticFiles

    _frontend_dir = "../frontend/dist"  # 相对运行目录(backend/),契约 §4.2
    import os as _os

    if _os.path.isdir(_frontend_dir):
        app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
    else:
        # 兜底:前端目录不存在时不挂载(仅提供 API)
        print(f"[startup] 前端目录不存在,跳过静态托管:{_os.path.abspath(_frontend_dir)}")
except Exception as exc:  # noqa: BLE001 - 静态托管失败不影响 API
    print(f"[startup] 静态托管初始化失败:{exc}")


# SPA fallback:前端 history 路由刷新(如 /note/<id>)时 StaticFiles 找不到文件 → 返回 index.html
@app.exception_handler(StarletteHTTPException)
async def _spa_fallback(request, exc):
    if exc.status_code == 404:
        import os as _os2
        _idx = _os2.path.abspath("../frontend/dist/index.html")
        if _os2.path.isfile(_idx):
            return FileResponse(_idx)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


if __name__ == "__main__":
    import uvicorn

    print(f"启动服务: http://{HOST}:{PORT}")
    uvicorn.run("src.main:app", host=HOST, port=PORT, reload=DEBUG)
