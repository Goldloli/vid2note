"""Upload API contracts."""

from pydantic import BaseModel


class UploadResponse(BaseModel):
    file_id: str
    filename: str
    size: int
