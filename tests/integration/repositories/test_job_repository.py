import asyncio
from datetime import UTC, datetime, timedelta

from app.core.database import get_sessionmaker
from app.models import Job, JobStatus
from app.repositories.job_repository import JobRepository

NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
LEASE = timedelta(seconds=30)


async def create_job(*, next_retry_at: datetime = NOW, max_attempts: int = 5) -> str:
    async with get_sessionmaker()() as db:
        job = await JobRepository(db).create(
            url="https://example.com/webhook",
            payload={"payment_id": "pay_123"},
            max_attempts=max_attempts,
            next_retry_at=next_retry_at,
        )
        await db.commit()
        return job.id


async def claim(now: datetime = NOW) -> Job | None:
    async with get_sessionmaker()() as db:
        job = await JobRepository(db).claim_next(now=now, lease=LEASE)
        await db.commit()
        return job


async def finish(job_id: str, **outcome) -> bool:
    async with get_sessionmaker()() as db:
        finished = await JobRepository(db).finish(job_id, **outcome)
        await db.commit()
        return finished


async def get_job(job_id: str) -> Job:
    async with get_sessionmaker()() as db:
        return await db.get(Job, job_id)


async def test_claim_marks_due_job_running():
    job_id = await create_job()

    job = await claim()

    assert job.id == job_id
    assert job.status == JobStatus.RUNNING
    assert job.attempts == 1
    assert job.next_retry_at is None
    assert job.locked_until == NOW + LEASE


async def test_claim_skips_job_not_yet_due():
    await create_job(next_retry_at=NOW + timedelta(seconds=1))

    assert await claim() is None


async def test_claim_picks_the_earliest_due_job():
    await create_job(next_retry_at=NOW - timedelta(seconds=1))
    earliest_id = await create_job(next_retry_at=NOW - timedelta(seconds=5))

    job = await claim()

    assert job.id == earliest_id


async def test_claim_skips_jobs_locked_by_another_worker():
    first_id = await create_job(next_retry_at=NOW - timedelta(seconds=1))
    second_id = await create_job()

    async with get_sessionmaker()() as holding:
        held = await JobRepository(holding).claim_next(now=NOW, lease=LEASE)
        held_id = held.id
        async with asyncio.timeout(5):
            other = await claim()
            nothing = await claim()
        await holding.rollback()

    assert held_id == first_id
    assert other.id == second_id
    assert nothing is None


async def test_concurrent_claims_never_share_a_job():
    job_ids = [await create_job() for _ in range(10)]

    claimed = await asyncio.gather(*(claim() for _ in range(20)))

    claimed_ids = [job.id for job in claimed if job is not None]
    assert sorted(claimed_ids) == sorted(job_ids)


async def test_claim_reclaims_job_once_lease_expires():
    job_id = await create_job()
    await claim()

    assert await claim(NOW + LEASE - timedelta(seconds=1)) is None
    reclaimed = await claim(NOW + LEASE)

    assert reclaimed.id == job_id
    assert reclaimed.attempts == 2


async def test_finish_records_outcome_and_releases_lease():
    job_id = await create_job()
    job = await claim()
    retry_at = NOW + timedelta(seconds=2)

    finished = await finish(
        job_id,
        attempt=job.attempts,
        status=JobStatus.PENDING,
        next_retry_at=retry_at,
        last_error="HTTP 503",
    )

    stored = await get_job(job_id)
    assert finished
    assert stored.status == JobStatus.PENDING
    assert stored.attempts == 1
    assert stored.next_retry_at == retry_at
    assert stored.locked_until is None
    assert stored.last_error == "HTTP 503"


async def test_finish_from_an_expired_lease_is_ignored():
    job_id = await create_job()
    stale = await claim()
    await claim(NOW + LEASE)

    finished = await finish(job_id, attempt=stale.attempts, status=JobStatus.COMPLETED)

    stored = await get_job(job_id)
    assert not finished
    assert stored.status == JobStatus.RUNNING
    assert stored.attempts == 2


async def test_abandoned_final_attempt_is_marked_dead():
    job_id = await create_job(max_attempts=1)
    await claim()

    assert await claim(NOW + LEASE) is None
    async with get_sessionmaker()() as db:
        marked = await JobRepository(db).mark_abandoned_as_dead(now=NOW + LEASE)
        await db.commit()

    stored = await get_job(job_id)
    assert marked == 1
    assert stored.status == JobStatus.DEAD
    assert stored.locked_until is None
    assert stored.last_error == "Lease expired on the final attempt"
