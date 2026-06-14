"""FastAPI 入口"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from vid2note_server.api import tasks, process, upload, config, models, events, logs

app = FastAPI(title="vid2note", version="0.1.0")

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

@app.get("/health")
async def health():
    return {"status": "ok"}
