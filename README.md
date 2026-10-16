# Retry Scheduler

A small internal service that accepts jobs (a target URL plus a JSON payload), delivers them to a downstream system, retries transient failures with exponential backoff and tracks each job's lifecycle until it completes, fails permanently or is dead-lettered.

FastAPI · SQLAlchemy 2 (async) · PostgreSQL · Alembic · pytest + testcontainers · Docker

Design and reasoning — job lifecycle, retry rules, duplicate processing, multiple workers and testing: [docs/design.md](docs/design.md).

## Quick start

```bash
./scripts/dev.sh                   # local: .venv + deps, Postgres in Docker, migrations, API with --reload
docker compose up --build          # or everything in containers (only Docker needed)
```

Either way the API, with its background worker, listens on `http://localhost:8000` (`PORT=...` for `dev.sh`, `API_PORT=...` for compose) and applies the migrations before starting. Interactive docs live at `/docs`.

```bash
curl -s -X POST localhost:8000/jobs/ -H 'content-type: application/json' \
  -d '{"url": "https://example.com/webhook", "payload": {"payment_id": "pay_123", "status": "failed"}}'

curl -s localhost:8000/jobs/<id>/
```

The worker logs one line per attempt, e.g. `Job job_… attempt 1/5 -> pending (HTTP 429)`.

## Running locally

Requirements: Docker and Python 3.14.

| Script | What it does |
|---|---|
| `scripts/dev.sh` | creates `.venv` and installs `requirements-dev.txt` if needed, `docker compose up -d --wait db`, `alembic upgrade head`, `uvicorn --reload` |
| `scripts/start.sh` | `alembic upgrade head`, then `exec uvicorn` (the container entrypoint) |

`cp .env.example .env` is optional: every setting has a default. With the `.venv` that `dev.sh` created:

```bash
source .venv/bin/activate
pytest tests                       # whole suite; testcontainers starts its own Postgres
pytest tests/unit                  # unit tests only, no Docker needed
ruff check . && ruff format --check .
```

New migrations: `alembic -c migrations/alembic.ini revision --autogenerate -m "..."`.

To see every lifecycle path within seconds, put fast settings in `.env` (the `api` container reads it too):

```dotenv
MAX_ATTEMPTS=3
RETRY_BASE_DELAY_SECONDS=0.2
RETRY_MAX_DELAY_SECONDS=1
SIMULATED_FAILURE_RATE=0.7
```

## API

| Method | Path | Result |
|---|---|---|
| `POST` | `/jobs/` | `201` with the created job |
| `GET` | `/jobs/{id}/` | `200` with the job, `404` if unknown |
| `GET` | `/health` | `200 {"status": "ok"}` once the database answers |

`/jobs` and `/jobs/{id}` without the trailing slash redirect (`307`) to the canonical paths.

`POST /jobs/` takes `{"url": <http(s) URL>, "payload": <JSON object>}`; both endpoints answer the same job representation:

```json
{
  "id": "job_8ffdc374bba04e3f815837dd936c31f2",
  "status": "pending",
  "attempts": 1,
  "max_attempts": 5,
  "next_retry_at": "2026-10-16T18:11:52.755070Z",
  "last_error": "HTTP 429",
  "created_at": "2026-10-16T18:11:50.604518Z",
  "updated_at": "2026-10-16T18:11:51.762011Z"
}
```

Errors share one envelope, e.g. `404`:

```json
{"error": "NOT_FOUND", "message": "Job not found", "details": {}}
```

An invalid body answers `422` with `"error": "VALIDATION_ERROR"` and the per-field problems in `details`.

## Configuration

Environment variables (or `.env`), all optional:

| Variable | Default | Purpose |
|---|---|---|
| `DB_DRIVER` | `postgresql+asyncpg` | SQLAlchemy driver |
| `DB_HOST` / `DB_PORT` | `localhost` / `5433` | Database address (compose publishes Postgres on 5433) |
| `DB_USER` / `DB_PASSWORD` / `DB_NAME` | `postgres` / `postgres` / `retry_scheduler` | Database credentials |
| `MAX_ATTEMPTS` | `5` | Attempts per job, the first one included |
| `RETRY_BASE_DELAY_SECONDS` | `1.0` | First backoff delay |
| `RETRY_MAX_DELAY_SECONDS` | `60.0` | Backoff cap |
| `WORKER_CONCURRENCY` | `4` | Worker loops per process (`0` disables the worker) |
| `POLL_INTERVAL_SECONDS` | `1.0` | Idle wait between claims when nothing is due |
| `LEASE_SECONDS` | `30.0` | How long a claim owns a job; must exceed the delivery timeout |
| `DELIVERY_TIMEOUT_SECONDS` | `10.0` | Hard limit for one delivery attempt |
| `SIMULATED_FAILURE_RATE` | `0.3` | Share of simulated deliveries that fail |
| `SIMULATED_MAX_LATENCY_SECONDS` | `0.5` | Upper bound of the simulated latency |
| `SIMULATED_SEED` | unset | Seed for reproducible simulated outcomes |

## Assumptions

- **Delivery is simulated.** The brief does not require real HTTP calls, so `SimulatedDeliveryService` stands in for the downstream: random latency, `200` most of the time, otherwise `429`, `500`, `503`, `400` or a timeout. It sits behind the `DeliveryService` abstraction; a real HTTP client is one more implementation, with no change to the worker.
- "Maximum number of retries" is modelled as `MAX_ATTEMPTS`, the total number of attempts, to avoid off-by-one ambiguity. Each job stores its own `max_attempts` at creation, so a config change never alters in-flight jobs.
- `failed` is a permanent downstream rejection; `dead` is the dead letter for exhausted transient failures.
- The payload must be a JSON object and the URL `http(s)`. As an internal service with simulated delivery, there is no authentication (per the brief) and no URL allowlist.
- Retries are scheduled, not exact: a job becomes eligible at `next_retry_at` and is picked up within one poll interval. All times are UTC.

## Trade-offs

- **PostgreSQL as the queue.** `FOR UPDATE SKIP LOCKED` gives safe concurrent claiming with durable state and a single dependency. A dedicated broker would add throughput and push-based wake-ups at the cost of another moving part and a second source of truth.
- **Worker inside the API process.** Started from the FastAPI lifespan, so one `docker compose up` runs everything. Splitting it into its own deployment is configuration (`WORKER_CONCURRENCY=0` on the API) plus an entrypoint.
- **Polling** every `POLL_INTERVAL_SECONDS` when idle, instead of `LISTEN/NOTIFY`: simple and robust, at the cost of up to one interval of pickup latency.
- **No jitter, `Retry-After` ignored.** Keeps retry timing predictable and exactly testable; the price is synchronised retries when many jobs fail at once.
- **Application clock for scheduling and leases.** The worker takes an injectable clock, which makes timing tests deterministic. Across many hosts, clock skew would shift lease expiry; the database clock is the safer reference there.
- **Single-stage Docker image.** Every dependency installs from a prebuilt wheel, so a builder stage would not shrink the image.
- **The job response omits `url` and `payload`.** It reports lifecycle state only; payloads can be large or sensitive.

## What I would improve with more time

- **Attempt history**: a `job_attempts` table (timestamps, status code, error) to show the whole timeline of a job, not only its latest state.
- **Dead-letter operations**: `GET /jobs/?status=dead` and a requeue endpoint.
- **Idempotent job creation**: an `Idempotency-Key` header on `POST /jobs/` so client retries do not create duplicate jobs.
- **Scale and housekeeping**: database time for leases, a partial index on due `pending` jobs, retention for terminal jobs, and a separate worker deployment.
- **CI**: run `ruff` and `pytest` on every push.
