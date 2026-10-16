#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose up -d --wait db
alembic -c migrations/alembic.ini upgrade head
exec uvicorn app.main:app --reload --port "${PORT:-8000}"
