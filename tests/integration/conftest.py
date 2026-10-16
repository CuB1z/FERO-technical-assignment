from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from testcontainers.community.postgres import PostgresContainer

from app.core.config import settings
from app.core.database import get_engine
from app.main import app

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "migrations" / "alembic.ini"


@pytest.fixture(scope="session", autouse=True)
def database():
    with PostgresContainer("postgres:17-alpine") as postgres:
        settings.DB_HOST = postgres.get_container_host_ip()
        settings.DB_PORT = postgres.get_exposed_port(5432)
        settings.DB_USER = postgres.username
        settings.DB_PASSWORD = postgres.password
        settings.DB_NAME = postgres.dbname
        command.upgrade(Config(ALEMBIC_INI), "head")
        yield


@pytest.fixture(scope="session", autouse=True)
async def engine(database):
    yield get_engine()
    await get_engine().dispose()


@pytest.fixture(autouse=True)
async def clean_jobs(engine):
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE jobs"))


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
