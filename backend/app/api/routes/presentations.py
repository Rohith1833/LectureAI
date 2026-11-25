from typing import Optional
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.schemas.presentation import PresentationJobStatus
from app.services.presentation_pipeline import (
    create_presentation_job,
    get_presentation_file_info,
    get_presentation_job,
)

router = APIRouter()


class GeneratePresentationRequest(BaseModel):
    upload_id: str
    target_slide_count: Optional[int] = Field(
        default=None,
        ge=3,
        le=120,
        description="Target number of slides, or null for automatic sizing.",
    )


@router.post("/generate", response_model=PresentationJobStatus)
def start_presentation_generation(
    request: GeneratePresentationRequest,
    background_tasks: BackgroundTasks,
) -> PresentationJobStatus:
    """Start end-to-end textbook-to-PPTX generation for an uploaded PDF."""
    return create_presentation_job(
        request.upload_id,
        background_tasks,
        target_slide_count=request.target_slide_count,
    )


@router.get("/{job_id}", response_model=PresentationJobStatus)
def poll_presentation_status(job_id: str) -> PresentationJobStatus:
    """Poll real-time stage, progress, and preview data for a presentation job."""
    return get_presentation_job(job_id)


@router.get("/{job_id}/download")
def download_presentation(job_id: str):
    """Download the generated .pptx file."""
    file_path, download_name = get_presentation_file_info(job_id)
    return FileResponse(
        path=file_path,
        filename=download_name,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
