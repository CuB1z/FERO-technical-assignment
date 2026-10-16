import asyncio
import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.database import get_sessionmaker
from app.models import Job, JobStatus
from app.repositories.job_repository import JobRepository
from app.services.delivery_service import DeliveryService, SimulatedDeliveryService
from app.worker.retry_policy import RetryPolicy

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(UTC)


class JobRunner:
    def __init__(
        self,
        *,
        delivery: DeliveryService,
        policy: RetryPolicy,
        lease: timedelta,
        delivery_timeout: float,
        poll_interval: float,
        clock: Callable[[], datetime] = utc_now,
    ):
        self._delivery = delivery
        self._policy = policy
        self._lease = lease
        self._delivery_timeout = delivery_timeout
        self._poll_interval = poll_interval
        self._clock = clock

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                processed = await self.run_once()
            except Exception:
                logger.exception("Worker iteration failed")
                processed = False
            if not processed:
                with suppress(TimeoutError):
                    async with asyncio.timeout(self._poll_interval):
                        await stop.wait()

    async def run_once(self) -> bool:
        job = await self._claim()
        if job is None:
            return False

        status_code = await self._deliver(job)
        decision = self._policy.decide(
            status_code, attempts=job.attempts, max_attempts=job.max_attempts
        )
        last_error = None
        if decision.status != JobStatus.COMPLETED:
            last_error = (
                "Delivery timed out" if status_code is None else f"HTTP {status_code}"
            )

        async with get_sessionmaker()() as db:
            recorded = await JobRepository(db).finish(
                job.id,
                attempt=job.attempts,
                status=decision.status,
                next_retry_at=(
                    self._clock() + decision.retry_in if decision.retry_in else None
                ),
                last_error=last_error,
            )
            await db.commit()

        if recorded:
            logger.info(
                "Job %s attempt %d/%d -> %s (%s)",
                job.id,
                job.attempts,
                job.max_attempts,
                decision.status,
                last_error or "delivered",
            )
        else:
            logger.warning(
                "Job %s attempt %d lost its lease, result discarded",
                job.id,
                job.attempts,
            )
        return True

    async def _claim(self) -> Job | None:
        now = self._clock()
        async with get_sessionmaker()() as db:
            jobs_repo = JobRepository(db)
            abandoned = await jobs_repo.mark_abandoned_as_dead(now=now)
            job = await jobs_repo.claim_next(now=now, lease=self._lease)
            await db.commit()
        if abandoned:
            logger.warning("Marked %d abandoned job(s) as dead", abandoned)
        return job

    async def _deliver(self, job: Job) -> int | None:
        try:
            async with asyncio.timeout(self._delivery_timeout):
                return await self._delivery.send(job.url, job.payload)
        except TimeoutError:
            return None


@asynccontextmanager
async def run_workers() -> AsyncGenerator[None]:
    runner = JobRunner(
        delivery=SimulatedDeliveryService(
            failure_rate=settings.SIMULATED_FAILURE_RATE,
            max_latency_seconds=settings.SIMULATED_MAX_LATENCY_SECONDS,
            seed=settings.SIMULATED_SEED,
        ),
        policy=RetryPolicy(
            base_delay_seconds=settings.RETRY_BASE_DELAY_SECONDS,
            max_delay_seconds=settings.RETRY_MAX_DELAY_SECONDS,
        ),
        lease=timedelta(seconds=settings.LEASE_SECONDS),
        delivery_timeout=settings.DELIVERY_TIMEOUT_SECONDS,
        poll_interval=settings.POLL_INTERVAL_SECONDS,
    )
    stop = asyncio.Event()
    workers = [
        asyncio.create_task(runner.run(stop))
        for _ in range(settings.WORKER_CONCURRENCY)
    ]
    try:
        yield
    finally:
        stop.set()
        await asyncio.gather(*workers)
