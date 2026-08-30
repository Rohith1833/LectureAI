from sqlalchemy.orm import Session
from fastapi import HTTPException
from typing import Optional
import json
import traceback
from loguru import logger
from pathlib import Path
from datetime import datetime

from app.schemas.artifact import ArtifactJobCreate, ArtifactJobRead, ArtifactStatus
from app.repositories.artifact_repository import ArtifactRepository
from app.models.knowledge import KnowledgeVersion
from app.schemas.knowledge import KnowledgeVersionStatus
from app.schemas.academic import AcademicNodeCategory

# For orchestration
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.document_repository import DocumentRepository
from app.services.retrieval.retrieval_service import RetrievalService
from app.services.retrieval.ranker import RankingWeights
from app.services.generation.groq_provider import GroqProvider
from app.services.generation.mock_provider import MockLLMProvider
from app.services.artifact.artifact_planner import ArtifactPlanner
from app.services.artifact.artifact_validator import ArtifactValidator, ArtifactValidationContext
from app.services.artifact.pptx_renderer import PPTXRenderer
from app.core.config import settings

def _get_provider():
    key = settings.GROQ_API_KEY
    if key and key.strip() and key.strip() != "test-groq-key":
        return GroqProvider()
    return MockLLMProvider(scenario="success")

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

    async def run_generation_pipeline(self, job_id: str) -> None:
        """
        End-to-end background orchestration of artifact generation:
        PENDING -> PLANNING -> RENDERING -> COMPLETED
        """
        logger.info(f"Starting background pipeline for artifact job {job_id}")
        
        try:
            # Transition to PLANNING
            job = self.repo.update_job_status(job_id, ArtifactStatus.PLANNING)
            if not job:
                logger.error(f"Job {job_id} not found when starting pipeline.")
                return
                
            # 1. Initialize services
            knowledge_repo = KnowledgeRepository(self.db)
            document_repo = DocumentRepository(self.db)
            
            # Recreate exactly what RetrievalService needs
            retrieval_service = RetrievalService(
                knowledge_repo=knowledge_repo,
                document_repo=document_repo,
                weights=RankingWeights(
                    title=0.3, content=0.1, coverage=0.15, type=0.1, 
                    relationship=0.1, evidence=0.1, passage=0.1, confidence=0.05
                )
            )
            llm_provider = _get_provider()
            
            planner = ArtifactPlanner(knowledge_repo, retrieval_service, llm_provider)
            validator = ArtifactValidator()
            renderer = PPTXRenderer()
            
            # Fetch knowledge version to build validation context
            kv = knowledge_repo.get_finalized_version(job.knowledge_version_id)
            if not kv:
                raise ValueError(f"Knowledge version {job.knowledge_version_id} not found during planning.")
                
            expected_units = set()
            valid_node_ids = set()
            for entity in kv.entities:
                valid_node_ids.add(entity.id)
                if entity.entity_type == AcademicNodeCategory.UNIT:
                    expected_units.add(entity.id)
                    
            # For strict subset of expected units based on config num_units
            num_units = job.config.get("num_units")
            if num_units and num_units < len(expected_units):
                # Just get the top N units preserving order - simplified logic for context
                sorted_units = sorted([e for e in kv.entities if e.entity_type == AcademicNodeCategory.UNIT], key=lambda x: x.id)
                expected_units = set(u.id for u in sorted_units[:num_units])
                
            # valid_evidence_ids logic would ideally be precomputed or retrieved.
            # For safety, we will let validator use a loose set or we must extract all evidence.
            # In Phase 9C, planner extracts evidence during its chunks. 
            # To avoid an expensive DB query here, we'll let Validator only assert what's provided, 
            # but ideally we supply all valid evidence IDs from the version.
            valid_evidence_ids = set()
            for entity in kv.entities:
                for ev in entity.evidence:
                    if ev.id:
                        valid_evidence_ids.add(ev.id)
            
            # 2. Planning (Phase 9C)
            plan = await planner.plan(ArtifactJobRead.model_validate(job))
            
            # 3. Validation (Phase 9D)
            context = ArtifactValidationContext(
                valid_node_ids=valid_node_ids,
                valid_evidence_ids=valid_evidence_ids,
                expected_units=expected_units,
                config=job.config
            )
            validation_result = validator.validate(plan, context)
            
            if not validation_result.is_valid:
                errors = [f"{e.category}: {e.message}" for e in validation_result.errors]
                raise ValueError(f"Validation failed: {'; '.join(errors)}")
                
            # 4. Transition to RENDERING
            job = self.repo.update_job_status(job_id, ArtifactStatus.RENDERING)
            
            # 5. Rendering (Phase 9B)
            # Output directory should be inside a generic artifacts dir
            out_dir = Path("data/artifacts")
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"artifact_{job_id}.pptx"
            
            result_path = renderer.render(plan, str(out_path))
            
            # 6. COMPLETED
            job.artifact_uri = str(result_path)
            job.status = ArtifactStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            self.db.commit()
            
            logger.info(f"Successfully completed artifact job {job_id}")

        except Exception as e:
            logger.error(f"Failed artifact pipeline for {job_id}: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Transition to FAILED
            try:
                # Need fresh DB session state if previous failed
                self.db.rollback()
                job = self.repo.get_job(job_id)
                if job:
                    job.status = ArtifactStatus.FAILED
                    job.error_message = str(e)
                    job.completed_at = datetime.utcnow()
                    self.db.commit()
            except Exception as inner_e:
                logger.error(f"Failed to save FAILED status for job {job_id}: {str(inner_e)}")
                self.db.rollback()
