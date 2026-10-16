from dataclasses import dataclass
from datetime import timedelta

from app.models import JobStatus

RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})


@dataclass(frozen=True)
class RetryDecision:
    status: JobStatus
    retry_in: timedelta | None = None


@dataclass(frozen=True)
class RetryPolicy:
    base_delay_seconds: float
    max_delay_seconds: float

    def decide(
        self, status_code: int | None, *, attempts: int, max_attempts: int
    ) -> RetryDecision:
        if status_code is not None and 200 <= status_code < 300:
            return RetryDecision(JobStatus.COMPLETED)
        if status_code is not None and status_code not in RETRYABLE_STATUS_CODES:
            return RetryDecision(JobStatus.FAILED)
        if attempts >= max_attempts:
            return RetryDecision(JobStatus.DEAD)
        return RetryDecision(JobStatus.PENDING, self.backoff(attempts))

    def backoff(self, attempt: int) -> timedelta:
        delay = self.base_delay_seconds * 2 ** (attempt - 1)
        return timedelta(seconds=min(delay, self.max_delay_seconds))
