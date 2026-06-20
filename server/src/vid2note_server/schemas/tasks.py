"""Task API contracts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CreateTaskRequest(BaseModel):
    video_url: str | None = None
    video_file: str | None = None
    pdf_file: str | None = None
    asr_provider: str = "funasr"
    llm_provider: str = "qwen"
    export_mindmap: bool = False


class RerunRequest(BaseModel):
    from_node: str | None = None


class TaskAcceptedResponse(BaseModel):
    task_id: str
    status: str
    message: str | None = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    progress: int = 0
    current_step: str = ""
    message: str | None = None
    video_url: str | None = None
    video_file: str | None = None
    audio_file: str | None = None
    srt_file: str | None = None
    srt_original_name: str | None = None
    txt_file: str | None = None
    pdf_file: str | None = None
    output_file: str | None = None
    mindmap_file: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    asr_provider: str | None = None
    export_mindmap: bool = False
    mindmap_format: str = "xmind"
    error_message: str | None = None
    retry_count: int = 0
    error_code: str | None = None
    error_retryable: bool = False
    rerun_from_node: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None


class TaskListResponse(BaseModel):
    tasks: list[TaskResponse]
    total: int
