#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q --disable-pip-version-check -r requirements-dev.txt

docker compose up -d --wait db
alembic -c migrations/alembic.ini upgrade head
exec uvicorn app.main:app --reload --port "${PORT:-8000}"
