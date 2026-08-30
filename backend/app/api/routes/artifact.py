from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.schemas.artifact import ArtifactJobCreate, ArtifactJobRead
from app.services.artifact.artifact_service import ArtifactService

router = APIRouter()

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
    # background_tasks.add_task(svc.process_job, job.id) # To be implemented in 9C
    
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
        
    if not job.artifact_uri:
        raise HTTPException(status_code=404, detail="Artifact URI not found")
        
    # Phase 9B will implement file streaming. For now, return the URI path.
    return {"download_url": job.artifact_uri}
