from fastapi import APIRouter, BackgroundTasks

from app.schemas.job import (
    JobCreate,
    JobCreateResponse,
    JobCreateResponseData,
    JobStatusResponse,
    JobListResponse,
)
from app.services import job_service

router = APIRouter()


@router.post("/jobs", response_model=JobCreateResponse)
async def create_job(payload: JobCreate, background_tasks: BackgroundTasks) -> JobCreateResponse:
    """Create a new presentation compiler background job."""
    res = job_service.create_job(
        payload.upload_id, background_tasks, ocr_strategy=payload.ocr_strategy
    )
    return JobCreateResponse(
        success=True,
        message="Job created",
        data=JobCreateResponseData(job_id=res["job_id"], status=res["status"]),
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Retrieve details and progress status for a specific job."""
    status_data = job_service.get_job_by_id(job_id)
    return JobStatusResponse(success=True, data=status_data)


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs() -> JobListResponse:
    """List all processing jobs, sorted newest first."""
    jobs = job_service.list_all_jobs_sorted()
    return JobListResponse(success=True, data=jobs)
