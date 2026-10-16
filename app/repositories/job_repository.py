from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job


class JobRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        url: str,
        payload: dict[str, Any],
        max_attempts: int,
        next_retry_at: datetime,
    ) -> Job:
        job = Job(
            url=url,
            payload=payload,
            max_attempts=max_attempts,
            next_retry_at=next_retry_at,
        )
        self.db.add(job)
        await self.db.flush()
        return job

    async def get(self, job_id: str) -> Job | None:
        return await self.db.get(Job, job_id)
