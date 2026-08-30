from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
import os

from app.db.session import get_db, SessionLocal
from app.schemas.artifact import ArtifactJobCreate, ArtifactJobRead, ArtifactStatus
from app.services.artifact.artifact_service import ArtifactService
import asyncio

router = APIRouter()

async def background_artifact_generation(job_id: str):
    """
    Background worker to run artifact generation with its own database session.
    """
    db = SessionLocal()
    try:
        svc = ArtifactService(db)
        await svc.run_generation_pipeline(job_id)
    finally:
        db.close()

@router.post("/generate", response_model=ArtifactJobRead)
def create_artifact_job(
    request: ArtifactJobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Start a new artifact generation job.
    """
    svc = ArtifactService(db)
    job = svc.create_artifact_job(request)
    
    # Trigger background task for Planning and Rendering (Phase 9B & 9C)
    background_tasks.add_task(background_artifact_generation, job.id)
    
    return job

@router.get("/jobs/{upload_id}", response_model=List[ArtifactJobRead])
def list_jobs_for_document(
    upload_id: str,
    db: Session = Depends(get_db)
):
    """
    List all artifact generation jobs for a given document upload.
    """
    svc = ArtifactService(db)
    return svc.list_jobs_for_document(upload_id)

@router.get("/{job_id}", response_model=ArtifactJobRead)
def get_job_status(
    job_id: str,
    db: Session = Depends(get_db)
):
    """
    Poll the status of a specific artifact generation job.
    """
    svc = ArtifactService(db)
    job = svc.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.get("/{job_id}/download")
def download_artifact(
    job_id: str,
    db: Session = Depends(get_db)
):
    """
    Download the generated artifact.
    """
    svc = ArtifactService(db)
    job = svc.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    from app.schemas.artifact import ArtifactStatus
    if job.status != ArtifactStatus.COMPLETED.value:
        raise HTTPException(status_code=400, detail="Artifact is not ready for download or job failed")
        
    if not job.artifact_uri or not os.path.exists(job.artifact_uri):
        raise HTTPException(status_code=404, detail="Artifact file not found")
        
    # Phase 9E file streaming
    return FileResponse(
        path=job.artifact_uri, 
        filename=os.path.basename(job.artifact_uri),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
