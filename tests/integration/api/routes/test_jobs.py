import pytest

from app.core.config import settings
from app.core.database import get_sessionmaker
from app.models import Job

JOB = {
    "url": "https://example.com/webhook",
    "payload": {"payment_id": "pay_123", "status": "failed"},
}


async def test_create_job_returns_pending_job(client):
    response = await client.post("/jobs/", json=JOB)

    assert response.status_code == 201
    body = response.json()
    assert body["id"].startswith("job_")
    assert body["status"] == "pending"
    assert body["attempts"] == 0
    assert body["max_attempts"] == settings.MAX_ATTEMPTS
    assert body["next_retry_at"] is not None
    assert body["last_error"] is None


async def test_create_job_persists_url_and_payload(client):
    job_id = (await client.post("/jobs/", json=JOB)).json()["id"]

    async with get_sessionmaker()() as db:
        job = await db.get(Job, job_id)

    assert job.url == JOB["url"]
    assert job.payload == JOB["payload"]


async def test_get_job_returns_stored_job(client):
    created = (await client.post("/jobs/", json=JOB)).json()

    response = await client.get(f"/jobs/{created['id']}/")

    assert response.status_code == 200
    assert response.json() == created


async def test_get_unknown_job_returns_not_found(client):
    response = await client.get("/jobs/job_missing/")

    assert response.status_code == 404
    assert response.json()["error"] == "NOT_FOUND"


@pytest.mark.parametrize(
    "body",
    [
        {"url": "not-a-url", "payload": {}},
        {"url": "ftp://example.com", "payload": {}},
        {"url": "https://example.com", "payload": ["not", "an", "object"]},
        {"payload": {}},
        {"url": "https://example.com"},
    ],
)
async def test_create_job_rejects_invalid_body(client, body):
    response = await client.post("/jobs/", json=body)

    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"
