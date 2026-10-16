import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, column, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"


def _new_job_id() -> str:
    return f"job_{uuid.uuid4().hex}"


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(column("status").in_(list(JobStatus)), name="ck_jobs_status"),
        Index("ix_jobs_status_next_retry_at", "status", "next_retry_at"),
    )

    id: Mapped[str] = mapped_column(primary_key=True, default=_new_job_id)
    url: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[JobStatus] = mapped_column(String(16), default=JobStatus.PENDING)
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int]
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
