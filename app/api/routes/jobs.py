from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_job_service
from app.schemas.job import JobCreateRequest, JobResponse
from app.services.job_service import JobService

router = APIRouter()

JobServiceDep = Annotated[JobService, Depends(get_job_service)]


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_job(data: JobCreateRequest, service: JobServiceDep) -> JobResponse:
    return await service.create(url=str(data.url), payload=data.payload)


@router.get("/{job_id}/")
async def get_job(job_id: str, service: JobServiceDep) -> JobResponse:
    return await service.get(job_id)
