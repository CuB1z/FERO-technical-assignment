from typing import Annotated

from fastapi import Depends

from app.core.database import DbSession
from app.repositories.job_repository import JobRepository
from app.services.job_service import JobService


def get_job_repository(db: DbSession) -> JobRepository:
    return JobRepository(db)


def get_job_service(
    jobs_repo: Annotated[JobRepository, Depends(get_job_repository)],
) -> JobService:
    return JobService(jobs_repo)
