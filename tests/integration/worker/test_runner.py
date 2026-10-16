import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.database import get_sessionmaker
from app.models import Job, JobStatus
from app.repositories.job_repository import JobRepository
from app.services.delivery_service import DeliveryService
from app.worker.retry_policy import RetryPolicy
from app.worker.runner import JobRunner
from tests.conftest import ScriptedDeliveryService

NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
LEASE = timedelta(seconds=30)
URL = "https://example.com/webhook"
PAYLOAD = {"payment_id": "pay_123"}


class FakeClock:
    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class HangingDeliveryService(DeliveryService):
    async def send(self, url: str, payload: dict[str, Any]) -> int:
        await asyncio.sleep(10)
        return 200


def make_runner(delivery: DeliveryService, clock: FakeClock) -> JobRunner:
    return JobRunner(
        delivery=delivery,
        policy=RetryPolicy(base_delay_seconds=1, max_delay_seconds=60),
        lease=LEASE,
        delivery_timeout=0.05,
        poll_interval=0.01,
        clock=clock,
    )


async def create_job(*, max_attempts: int = 5) -> str:
    async with get_sessionmaker()() as db:
        job = await JobRepository(db).create(
            url=URL, payload=PAYLOAD, max_attempts=max_attempts, next_retry_at=NOW
        )
        await db.commit()
        return job.id


async def get_job(job_id: str) -> Job:
    async with get_sessionmaker()() as db:
        return await db.get(Job, job_id)


async def statuses(job_ids: list[str]) -> set[JobStatus]:
    return {(await get_job(job_id)).status for job_id in job_ids}


async def test_successful_delivery_completes_job():
    job_id = await create_job()
    delivery = ScriptedDeliveryService(200)

    assert await make_runner(delivery, FakeClock(NOW)).run_once()

    job = await get_job(job_id)
    assert delivery.calls == [(URL, PAYLOAD)]
    assert job.status == JobStatus.COMPLETED
    assert job.attempts == 1
    assert job.next_retry_at is None
    assert job.last_error is None


async def test_transient_failures_are_retried_with_backoff_until_success():
    job_id = await create_job()
    clock = FakeClock(NOW)
    runner = make_runner(ScriptedDeliveryService(503, None, 200), clock)

    await runner.run_once()
    job = await get_job(job_id)
    assert (job.status, job.attempts, job.last_error) == (
        JobStatus.PENDING,
        1,
        "HTTP 503",
    )
    assert job.next_retry_at == NOW + timedelta(seconds=1)
    assert not await runner.run_once()

    clock.advance(1)
    await runner.run_once()
    job = await get_job(job_id)
    assert (job.status, job.attempts, job.last_error) == (
        JobStatus.PENDING,
        2,
        "Delivery timed out",
    )
    assert job.next_retry_at == clock.now + timedelta(seconds=2)

    clock.advance(2)
    await runner.run_once()
    job = await get_job(job_id)
    assert (job.status, job.attempts, job.last_error) == (JobStatus.COMPLETED, 3, None)


async def test_exhausted_retries_mark_job_dead():
    job_id = await create_job(max_attempts=3)
    clock = FakeClock(NOW)
    runner = make_runner(ScriptedDeliveryService(500, 500, 500), clock)

    for _ in range(3):
        assert await runner.run_once()
        clock.advance(60)

    job = await get_job(job_id)
    assert job.status == JobStatus.DEAD
    assert job.attempts == 3
    assert job.next_retry_at is None
    assert job.last_error == "HTTP 500"


async def test_permanent_failure_is_not_retried():
    job_id = await create_job()
    clock = FakeClock(NOW)
    delivery = ScriptedDeliveryService(400)
    runner = make_runner(delivery, clock)

    await runner.run_once()
    clock.advance(3600)

    job = await get_job(job_id)
    assert not await runner.run_once()
    assert len(delivery.calls) == 1
    assert job.status == JobStatus.FAILED
    assert job.last_error == "HTTP 400"


async def test_slow_delivery_is_cut_off_and_retried():
    job_id = await create_job()

    await make_runner(HangingDeliveryService(), FakeClock(NOW)).run_once()

    job = await get_job(job_id)
    assert job.status == JobStatus.PENDING
    assert job.last_error == "Delivery timed out"


async def test_job_abandoned_on_final_attempt_is_marked_dead():
    job_id = await create_job(max_attempts=1)
    async with get_sessionmaker()() as db:
        await JobRepository(db).claim_next(now=NOW, lease=LEASE)
        await db.commit()

    clock = FakeClock(NOW + LEASE)
    assert not await make_runner(ScriptedDeliveryService(), clock).run_once()

    job = await get_job(job_id)
    assert job.status == JobStatus.DEAD


async def test_run_processes_jobs_until_stopped():
    job_ids = [await create_job() for _ in range(3)]
    runner = make_runner(ScriptedDeliveryService(200, 200, 200), FakeClock(NOW))
    stop = asyncio.Event()

    worker = asyncio.create_task(runner.run(stop))
    async with asyncio.timeout(5):
        while await statuses(job_ids) != {JobStatus.COMPLETED}:
            await asyncio.sleep(0.01)
    stop.set()

    await asyncio.wait_for(worker, timeout=1)
