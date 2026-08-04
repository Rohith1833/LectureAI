import asyncio
import json
import os
import uuid
from typing import List, Dict, Any
from fastapi import HTTPException, status, BackgroundTasks
from loguru import logger

from app.schemas.job import JobState, JobStage, JobStatusResponseData, PipelineStep
from app.utils.timestamps import utc_now
from app.agents.document_agent import run_document_agent
from app.services.ocr.page_detector import OCRStrategy

from app.core.storage import METADATA_DIR, JOBS_DIR, UPLOADS_DIR

# Central transition matrix
ALLOWED_TRANSITIONS: Dict[JobState, set] = {
    JobState.UPLOADED: {JobState.QUEUED},
    JobState.QUEUED: {JobState.PROCESSING, JobState.CANCELLED},
    JobState.PROCESSING: {JobState.PROCESSING, JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED},
    JobState.COMPLETED: set(),
    JobState.FAILED: set(),
    JobState.CANCELLED: set(),
}


def validate_state_transition(current_state: JobState, next_state: JobState) -> None:
    """Validate that transition is allowed by the lifecycle state machine."""
    allowed = ALLOWED_TRANSITIONS.get(current_state, set())
    if next_state not in allowed:
        logger.warning(
            "Invalid state transition attempted: '{}' -> '{}'",
            current_state.value,
            next_state.value,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid job state transition from {current_state.value} to {next_state.value}.",
        )


def _get_job_file_path(job_id: str) -> str:
    return os.path.join(JOBS_DIR, f"{job_id}.json")


def _read_job_document(job_id: str) -> Dict[str, Any]:
    """Read a job JSON file from disk."""
    # Validate UUID format
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Job ID format. Must be a valid UUID.",
        )

    path = _get_job_file_path(job_id)
    if not os.path.exists(path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found.",
        )

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to read job file '{}': {}", path, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read job metadata from storage.",
        )


def _write_job_document(job_id: str, data: Dict[str, Any]) -> None:
    """Write a job JSON file to disk."""
    path = _get_job_file_path(job_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error("Failed to write job file '{}': {}", path, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save job metadata to storage.",
        )


def update_job_status(
    job_id: str,
    next_state: JobState,
    next_stage: JobStage,
    progress: int,
    error: str = None,
    document_id: str = None,
) -> Dict[str, Any]:
    """Atomically transition state and write update to disk."""
    data = _read_job_document(job_id)
    current_state = JobState(data["status"])

    # Validate transition
    validate_state_transition(current_state, next_state)

    # Apply updates
    data["status"] = next_state.value
    data["current_stage"] = next_stage.value
    data["progress"] = progress
    data["updated_at"] = utc_now()
    if error:
        data["error"] = error
    if document_id:
        data["document_id"] = document_id

    _write_job_document(job_id, data)
    logger.info(
        "Job {} transitioned to state={}, stage={}, progress={}%",
        job_id,
        next_state.value,
        next_stage.value,
        progress,
    )
    return data


async def run_pdf_extraction_pipeline(job_id: str, upload_id: str) -> None:
    """Asynchronous background process executing layout extraction via DocumentAgent."""
    logger.info("PDF extraction pipeline task started for Job: {}", job_id)

    try:
        # Load job metadata to find requested OCR Strategy
        job_doc = _read_job_document(job_id)
        ocr_strategy_str = job_doc.get("ocr_strategy", "AUTO")
        strategy_enum = OCRStrategy(ocr_strategy_str)

        # 1. Transition to Preparing (5%)
        await asyncio.sleep(0.1)
        update_job_status(job_id, JobState.PROCESSING, JobStage.PREPARING, 5)

        # 2. Get target filename
        metadata_file = os.path.join(METADATA_DIR, f"{upload_id}.json")
        with open(metadata_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
        stored_filename = meta["stored_filename"]
        file_path = os.path.join(UPLOADS_DIR, stored_filename)

        # 3. Transition to Reading Document (20%)
        await asyncio.sleep(0.1)
        update_job_status(job_id, JobState.PROCESSING, JobStage.READING, 20)

        # 4. Transition to OCR stage (50%)
        update_job_status(job_id, JobState.PROCESSING, JobStage.OCR, 50)

        # Run DocumentAgent in a separate thread
        doc_id = await asyncio.to_thread(
            run_document_agent, upload_id, file_path, ocr_strategy=strategy_enum
        )

        # 5. Extract completed (100%)
        update_job_status(job_id, JobState.COMPLETED, JobStage.COMPLETED, 100, document_id=doc_id)

    except Exception as e:
        logger.error("Error during background PDF extraction for Job {}: {}", job_id, str(e))
        try:
            update_job_status(job_id, JobState.PROCESSING, JobStage.WAITING, 0)
            update_job_status(job_id, JobState.FAILED, JobStage.WAITING, 0, error=str(e))
        except Exception as fail_err:
            logger.error("Failed to mark job as failed: {}", str(fail_err))


def create_job(
    upload_id: str, background_tasks: BackgroundTasks, ocr_strategy: str = "AUTO"
) -> Dict[str, Any]:
    """Validate upload ID, initialize a new job JSON metadata, and start extraction."""
    # Verify upload metadata exists
    metadata_file = os.path.join(METADATA_DIR, f"{upload_id}.json")
    if not os.path.exists(metadata_file):
        logger.warning("Job creation rejected: Upload ID '{}' does not exist.", upload_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload ID not found. Verify file upload succeeded.",
        )

    # Prevent duplicate active jobs for the same upload ID (Optional check for robustness)
    # Check if there is an active running job already
    for filename in os.listdir(JOBS_DIR):
        if filename.endswith(".json"):
            try:
                with open(os.path.join(JOBS_DIR, filename), "r", encoding="utf-8") as f:
                    job = json.load(f)
                    if job["upload_id"] == upload_id and job["status"] in [
                        JobState.QUEUED.value,
                        JobState.PROCESSING.value,
                    ]:
                        logger.warning(
                            "Job creation rejected: Active job '{}' exists for upload '{}'.",
                            job["job_id"],
                            upload_id,
                        )
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="A processing job is already running for this upload ID.",
                        )
            except Exception as e:
                if isinstance(e, HTTPException):
                    raise e
                # ignore other parsing errors during search

    job_id = str(uuid.uuid4())
    now = utc_now()

    # Pre-populate AI Agent pipeline metadata in pending state
    pipeline_steps = [
        {"agent": "DocumentAgent", "status": "pending"},
        {"agent": "UnitAgent", "status": "pending"},
        {"agent": "OutlineAgent", "status": "pending"},
        {"agent": "ContentAgent", "status": "pending"},
        {"agent": "VisualAgent", "status": "pending"},
        {"agent": "QualityAgent", "status": "pending"},
        {"agent": "PPTAgent", "status": "pending"},
    ]

    job_data = {
        "job_id": job_id,
        "upload_id": upload_id,
        "status": JobState.QUEUED.value,
        "progress": 0,
        "current_stage": JobStage.WAITING.value,
        "created_at": now,
        "updated_at": now,
        "pipeline": pipeline_steps,
        "ocr_strategy": ocr_strategy,
        "error": None,
    }

    _write_job_document(job_id, job_data)
    logger.info("Job {} initialized and queued for upload ID {}", job_id, upload_id)

    # Queue background PDF extraction pipeline
    background_tasks.add_task(run_pdf_extraction_pipeline, job_id, upload_id)

    return {"job_id": job_id, "status": JobState.QUEUED}


def get_job_by_id(job_id: str) -> JobStatusResponseData:
    """Query job metadata details by UUID."""
    doc = _read_job_document(job_id)
    return JobStatusResponseData(
        job_id=doc["job_id"],
        upload_id=doc["upload_id"],
        status=JobState(doc["status"]),
        progress=doc["progress"],
        current_stage=JobStage(doc["current_stage"]),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
        pipeline=[PipelineStep(**step) for step in doc["pipeline"]],
        error=doc["error"],
        document_id=doc.get("document_id"),
    )


def list_all_jobs_sorted() -> List[JobStatusResponseData]:
    """Retrieve and list all jobs sorted from newest to oldest."""
    jobs = []
    for filename in os.listdir(JOBS_DIR):
        if filename.endswith(".json"):
            job_id = filename[:-5]
            try:
                jobs.append(get_job_by_id(job_id))
            except Exception:
                # Skip invalid or corrupted job documents
                pass

    # Sort descending by created_at
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return jobs
