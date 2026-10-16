from datetime import datetime
from typing import Any

from pydantic import BaseModel, HttpUrl

from app.models import JobStatus


class JobCreateRequest(BaseModel):
    url: HttpUrl
    payload: dict[str, Any]


class JobResponse(BaseModel):
    id: str
    status: JobStatus
    attempts: int
    max_attempts: int
    next_retry_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
