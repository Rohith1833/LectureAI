from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class JobState(str, Enum):
    """Enums representing the discrete stages of the Job Lifecycle."""

    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobStage(str, Enum):
    """Enums representing visual pipelines steps mapping future AI Agent runs."""

    WAITING = "Waiting"
    PREPARING = "Preparing"
    READING = "Reading Document"
    OCR = "OCR"
    UNIT_DETECTION = "Unit Detection"
    OUTLINE_GEN = "Outline Generation"
    CONTENT_GEN = "Content Generation"
    VISUAL_GEN = "Visual Generation"
    QUALITY_REVIEW = "Quality Review"
    PPT_GEN = "PPT Generation"
    EXPORT = "Export"
    COMPLETED = "Completed"


class PipelineStep(BaseModel):
    """Refers to individual Agent statuses in the compilation pipeline."""

    agent: str
    status: str = "pending"


# --- Request/Response Models ---


class JobCreate(BaseModel):
    """Request model for creating a job from an upload ID."""

    upload_id: str


class JobCreateResponseData(BaseModel):
    """Payload data returned on job creation."""

    job_id: str
    status: JobState


class JobCreateResponse(BaseModel):
    """Success wrapper for job creation endpoints."""

    success: bool
    message: str
    data: JobCreateResponseData


class JobStatusResponseData(BaseModel):
    """Payload data representing full job details and processing status."""

    job_id: str
    upload_id: str
    status: JobState
    progress: int = Field(..., ge=0, le=100)
    current_stage: JobStage
    created_at: str
    updated_at: str
    pipeline: List[PipelineStep]
    error: Optional[str] = None
    document_id: Optional[str] = None


class JobStatusResponse(BaseModel):
    """Standardized single-job detail wrapper response."""

    success: bool
    data: JobStatusResponseData


class JobListResponse(BaseModel):
    """Standardized list-jobs wrapper response."""

    success: bool
    data: List[JobStatusResponseData]
