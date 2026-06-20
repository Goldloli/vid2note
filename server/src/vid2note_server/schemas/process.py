"""Processing API contracts."""

from pydantic import BaseModel


class StartRequest(BaseModel):
    video_url: str | None = None
    video_file: str | None = None
    srt_file: str | None = None
    pdf_file: str | None = None
    asr_provider: str = "funasr"
    llm_provider: str = "qwen"
    export_mindmap: bool = False


class StartResponse(BaseModel):
    task_id: str
    status: str


class StatusResponse(BaseModel):
    task_id: str
    status: str
    progress: int
    current_step: str
    message: str | None = None
    error: str | None = None


class ResultResponse(BaseModel):
    task_id: str
    status: str
    progress: int
    artifacts: dict[str, str] | None = None
