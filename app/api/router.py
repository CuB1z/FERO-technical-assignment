from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.api.routes.jobs import router as jobs_router


def register_routers(app: FastAPI) -> None:
    app.include_router(health_router, tags=["health"])
    app.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
