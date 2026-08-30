from sqlalchemy.orm import Session
from fastapi import HTTPException
from typing import Optional

from app.schemas.artifact import ArtifactJobCreate, ArtifactJobRead, ArtifactStatus
from app.repositories.artifact_repository import ArtifactRepository
from app.models.knowledge import KnowledgeVersion
from app.schemas.knowledge import KnowledgeVersionStatus

class ArtifactService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ArtifactRepository(db)

    def create_artifact_job(self, request: ArtifactJobCreate) -> ArtifactJobRead:
        """
        Create a new artifact job, enforcing strict version locking and validation.
        """
        # Validate knowledge_version_id
        kv = self.db.query(KnowledgeVersion).filter(
            KnowledgeVersion.id == request.knowledge_version_id
        ).first()
        
        if not kv:
            raise HTTPException(status_code=404, detail="Knowledge version not found.")
            
        if kv.upload_id != request.upload_id:
            raise HTTPException(
                status_code=400, 
                detail="Knowledge version does not belong to the requested upload_id."
            )
            
        if kv.status != KnowledgeVersionStatus.FINALIZED.value:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot generate artifact from unfinalized knowledge version. Status: {kv.status}"
            )
            
        job = self.repo.create_job(request)
        return ArtifactJobRead.model_validate(job)

    def get_job_status(self, job_id: str) -> Optional[ArtifactJobRead]:
        job = self.repo.get_job(job_id)
        if not job:
            return None
        return ArtifactJobRead.model_validate(job)

    def list_jobs_for_document(self, upload_id: str) -> list[ArtifactJobRead]:
        jobs = self.repo.list_jobs(upload_id)
        return [ArtifactJobRead.model_validate(j) for j in jobs]
