from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class FileSpec(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str


class ResizeParams(BaseModel):
    max_width: int = Field(default=1024, ge=1, le=8192)
    max_height: int = Field(default=1024, ge=1, le=8192)


class CreateBatchRequest(BaseModel):
    files: list[FileSpec] = Field(min_length=1)
    operation: Literal["resize"] = "resize"
    params: ResizeParams = ResizeParams()


class UploadTarget(BaseModel):
    job_id: UUID
    filename: str
    upload_url: str
    content_type: str  # the client must send this exact Content-Type header with the PUT


class CreateBatchResponse(BaseModel):
    batch_id: UUID
    expires_in: int
    uploads: list[UploadTarget]


class JobStatus(BaseModel):
    id: UUID
    filename: str
    status: str
    attempts: int
    error: str | None
    updated_at: datetime


class BatchStatus(BaseModel):
    batch_id: UUID
    status: Literal["awaiting_upload", "processing", "done", "partial_failure", "failed"]
    operation: str
    total: int
    counts: dict[str, int]
    created_at: datetime
    queued_at: datetime | None
    jobs: list[JobStatus]


class ResultLink(BaseModel):
    job_id: UUID
    filename: str
    download_url: str


class BatchResults(BaseModel):
    batch_id: UUID
    expires_in: int
    results: list[ResultLink]
