from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import register_routers
from app.core.config import APP_VERSION
from app.core.database import get_engine
from app.core.exceptions import register_exception_handlers


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    yield
    await get_engine().dispose()


app = FastAPI(
    title="Retry Scheduler",
    version=APP_VERSION,
    lifespan=lifespan,
)

register_exception_handlers(app)
register_routers(app)
