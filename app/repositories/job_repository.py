from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job, JobStatus


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

    async def claim_next(self, *, now: datetime, lease: timedelta) -> Job | None:
        due_job_id = (
            select(Job.id)
            .where(
                or_(
                    and_(Job.status == JobStatus.PENDING, Job.next_retry_at <= now),
                    and_(
                        Job.status == JobStatus.RUNNING,
                        Job.locked_until <= now,
                        Job.attempts < Job.max_attempts,
                    ),
                )
            )
            .order_by(Job.next_retry_at)
            .limit(1)
            .with_for_update(skip_locked=True)
            .scalar_subquery()
        )
        return await self.db.scalar(
            update(Job)
            .where(Job.id == due_job_id)
            .values(
                status=JobStatus.RUNNING,
                attempts=Job.attempts + 1,
                next_retry_at=None,
                locked_until=now + lease,
            )
            .returning(Job)
        )

    async def finish(
        self,
        job_id: str,
        *,
        attempt: int,
        status: JobStatus,
        next_retry_at: datetime | None = None,
        last_error: str | None = None,
    ) -> bool:
        result = await self.db.execute(
            update(Job)
            .where(
                Job.id == job_id,
                Job.status == JobStatus.RUNNING,
                Job.attempts == attempt,
            )
            .values(
                status=status,
                next_retry_at=next_retry_at,
                locked_until=None,
                last_error=last_error,
            )
        )
        return result.rowcount == 1

    async def mark_abandoned_as_dead(self, *, now: datetime) -> int:
        result = await self.db.execute(
            update(Job)
            .where(
                Job.status == JobStatus.RUNNING,
                Job.locked_until <= now,
                Job.attempts >= Job.max_attempts,
            )
            .values(
                status=JobStatus.DEAD,
                locked_until=None,
                last_error="Lease expired on the final attempt",
            )
        )
        return result.rowcount
