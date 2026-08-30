from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException

from app.models.artifact import ArtifactJob
from app.schemas.artifact import ArtifactJobCreate, ArtifactStatus

class ArtifactRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_job(self, create_data: ArtifactJobCreate, user_id: str = "anonymous") -> ArtifactJob:
        job = ArtifactJob(
            upload_id=create_data.upload_id,
            knowledge_version_id=create_data.knowledge_version_id,
            artifact_type=create_data.artifact_type.value,
            config=create_data.config,
            # No user identity required, but keeping a default column if it existed.
            # Wait, the artifact job model doesn't have user_id because the user said:
            # "Do not add mandatory user_id ownership unless the existing project already has a real authentication/user identity system."
        )
        self.db.add(job)
        try:
            self.db.commit()
            self.db.refresh(job)
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(status_code=400, detail="Invalid upload_id or knowledge_version_id")
        return job

    def get_job(self, job_id: str) -> Optional[ArtifactJob]:
        return self.db.query(ArtifactJob).filter(ArtifactJob.id == job_id).first()

    def list_jobs(self, upload_id: str) -> List[ArtifactJob]:
        return self.db.query(ArtifactJob).filter(ArtifactJob.upload_id == upload_id).order_by(ArtifactJob.created_at.desc()).all()

    def update_job_status(self, job_id: str, status: ArtifactStatus, error_message: Optional[str] = None) -> ArtifactJob:
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        current_status = ArtifactStatus(job.status)
        
        valid_transitions = {
            ArtifactStatus.PENDING: [ArtifactStatus.PLANNING],
            ArtifactStatus.PLANNING: [ArtifactStatus.RENDERING, ArtifactStatus.FAILED],
            ArtifactStatus.RENDERING: [ArtifactStatus.COMPLETED, ArtifactStatus.FAILED],
            ArtifactStatus.COMPLETED: [],
            ArtifactStatus.FAILED: []
        }
        
        if status not in valid_transitions[current_status]:
            raise ValueError(f"Invalid state transition from {current_status.value} to {status.value}")
        
        job.status = status.value
        if error_message:
            job.error_message = error_message
        
        if status in (ArtifactStatus.COMPLETED, ArtifactStatus.FAILED):
            from datetime import datetime
            job.completed_at = datetime.utcnow()
            
        self.db.commit()
        self.db.refresh(job)
        return job


    def save_plan(self, job_id: str, plan: dict) -> ArtifactJob:
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        job.plan = plan
        self.db.commit()
        self.db.refresh(job)
        return job

    def set_artifact_uri(self, job_id: str, uri: str) -> ArtifactJob:
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        job.artifact_uri = uri
        self.db.commit()
        self.db.refresh(job)
        return job
