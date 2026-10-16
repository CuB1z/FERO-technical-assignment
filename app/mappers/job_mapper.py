from app.models import Job
from app.schemas.job import JobResponse


class JobMapper:
    @staticmethod
    def out(job: Job) -> JobResponse:
        return JobResponse(
            id=job.id,
            status=job.status,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            next_retry_at=job.next_retry_at,
            last_error=job.last_error,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
