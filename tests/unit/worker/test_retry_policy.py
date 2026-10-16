from datetime import timedelta

import pytest

from app.models import JobStatus
from app.worker.retry_policy import RetryDecision, RetryPolicy

POLICY = RetryPolicy(base_delay_seconds=1, max_delay_seconds=10)


@pytest.mark.parametrize("status_code", [200, 201, 204, 299])
def test_success_completes(status_code):
    decision = POLICY.decide(status_code, attempts=1, max_attempts=5)

    assert decision == RetryDecision(JobStatus.COMPLETED)


@pytest.mark.parametrize("status_code", [None, 408, 429, 500, 502, 503, 504])
def test_transient_failure_schedules_retry(status_code):
    decision = POLICY.decide(status_code, attempts=1, max_attempts=5)

    assert decision == RetryDecision(JobStatus.PENDING, timedelta(seconds=1))


@pytest.mark.parametrize("status_code", [None, 503])
def test_transient_failure_on_last_attempt_is_dead(status_code):
    decision = POLICY.decide(status_code, attempts=5, max_attempts=5)

    assert decision == RetryDecision(JobStatus.DEAD)


@pytest.mark.parametrize("status_code", [301, 400, 401, 403, 404, 409, 422, 501])
def test_permanent_failure_fails_without_retry(status_code):
    decision = POLICY.decide(status_code, attempts=1, max_attempts=5)

    assert decision == RetryDecision(JobStatus.FAILED)


def test_permanent_failure_on_last_attempt_still_fails():
    decision = POLICY.decide(400, attempts=5, max_attempts=5)

    assert decision == RetryDecision(JobStatus.FAILED)


def test_backoff_doubles_each_attempt():
    delays = [POLICY.backoff(attempt) for attempt in range(1, 5)]

    assert delays == [timedelta(seconds=s) for s in (1, 2, 4, 8)]


@pytest.mark.parametrize("attempt", [5, 6, 50])
def test_backoff_is_capped_at_max_delay(attempt):
    assert POLICY.backoff(attempt) == timedelta(seconds=10)
