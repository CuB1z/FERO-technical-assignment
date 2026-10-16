from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.mappers.job_mapper import JobMapper
from app.repositories.job_repository import JobRepository
from app.schemas.job import JobResponse


class JobService:
    def __init__(self, jobs_repo: JobRepository):
        self._jobs_repo = jobs_repo

    async def create(self, *, url: str, payload: dict[str, Any]) -> JobResponse:
        job = await self._jobs_repo.create(
            url=url,
            payload=payload,
            max_attempts=settings.MAX_ATTEMPTS,
            next_retry_at=datetime.now(UTC),
        )
        return JobMapper.out(job)

    async def get(self, job_id: str) -> JobResponse:
        job = await self._jobs_repo.get(job_id)
        if job is None:
            raise NotFoundError("Job not found")
        return JobMapper.out(job)
