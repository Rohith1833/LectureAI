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
from app.services.generation.errors import LLMProviderError
from app.models.artifact import ArtifactJob
import os
import pptx

def _get_provider(config: Optional[dict] = None):
    cfg = config or {}
    provider_name = cfg.get("provider") or getattr(settings, "LLM_PROVIDER", None) or os.environ.get("LLM_PROVIDER")
    if provider_name:
        provider_name = provider_name.strip().lower()

    if provider_name in ("mock", "test"):
        scenario = cfg.get("mock_scenario", "success")
        return MockLLMProvider(scenario=scenario)

    api_key = settings.GROQ_API_KEY
    if not api_key or not api_key.strip() or api_key.strip() == "test-groq-key":
        raise LLMProviderError(
            "Missing live provider configuration: GROQ_API_KEY environment variable is not configured. "
            "Mock provider is only available through explicit test/demo configuration (e.g. provider='mock' or LLM_PROVIDER=mock)."
        )
    return GroqProvider(api_key=api_key)

from app.services.artifact.selection_resolver import (
    resolve_effective_selection,
    resolve_effective_selection_for_job
)

class ArtifactService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ArtifactRepository(db)

    def create_artifact_job(self, request: ArtifactJobCreate) -> ArtifactJobRead:
        """
        Create a new artifact job, enforcing strict version locking, document association,
        and container selection validation.
        """
        try:
            effective_selection = resolve_effective_selection(
                db=self.db,
                version_id=request.knowledge_version_id,
                upload_id=request.upload_id,
                config=request.config
            )
        except ValueError as e:
            # Map validation errors: 404 only for missing KnowledgeVersion itself, 400 for container/contract errors
            err_msg = str(e)
            if err_msg.startswith("Knowledge version") and "not found" in err_msg.lower():
                raise HTTPException(status_code=404, detail=err_msg)
            raise HTTPException(status_code=400, detail=err_msg)

        # Persist the resolved selection into job config
        updated_config = dict(request.config)
        updated_config["selected_unit_ids"] = effective_selection.selected_container_ids
        updated_config["container_mode"] = effective_selection.container_mode.value
        updated_config["container_type"] = effective_selection.container_type
        updated_config["document_id"] = effective_selection.document_id
        if "num_units" in updated_config:
            del updated_config["num_units"]
        request.config = updated_config

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

    def recover_interrupted_jobs(self) -> int:
        """
        Scans for jobs left in PLANNING or RENDERING state (e.g. after a process crash/restart).
        Transitions them to FAILED with an explicit actionable message.
        Does NOT automatically resume or charge for interrupted work.
        Returns the count of recovered jobs.
        """
        in_flight_jobs = self.db.query(ArtifactJob).filter(
            ArtifactJob.status.in_([ArtifactStatus.PLANNING.value, ArtifactStatus.RENDERING.value])
        ).all()
        recovered = 0
        for job in in_flight_jobs:
            job.status = ArtifactStatus.FAILED.value
            job.error_message = (
                f"Job execution was interrupted while in {job.status} stage "
                "(server shutdown or background worker termination). "
                "Please submit a new generation request."
            )
            job.completed_at = datetime.utcnow()
            out_path = Path("data/artifacts") / f"artifact_{job.id}.pptx"
            if out_path.exists():
                try:
                    out_path.unlink()
                except Exception:
                    pass
            recovered += 1
        if recovered > 0:
            self.db.commit()
            logger.info(f"Recovered {recovered} interrupted artifact jobs to FAILED status.")
        return recovered

    async def run_generation_pipeline(self, job_id: str) -> None:
        """
        End-to-end background orchestration of artifact generation:
        PENDING -> PLANNING -> RENDERING -> COMPLETED
        """
        logger.info(f"Starting background pipeline for artifact job {job_id}")
        current_stage = "INITIALIZATION"
        out_path = Path("data/artifacts") / f"artifact_{job_id}.pptx"
        
        try:
            # Check current job state and reject duplicate execution
            existing_job = self.repo.get_job(job_id)
            if not existing_job:
                logger.error(f"Job {job_id} not found when starting pipeline.")
                return
            if existing_job.status in (ArtifactStatus.PLANNING.value, ArtifactStatus.RENDERING.value, ArtifactStatus.COMPLETED.value):
                logger.warning(f"Job {job_id} is already in {existing_job.status} state. Rejecting duplicate execution.")
                return

            # Transition to PLANNING
            current_stage = "PLANNING"
            job = self.repo.update_job_status(job_id, ArtifactStatus.PLANNING)
            if not job:
                logger.error(f"Job {job_id} not found when transitioning to PLANNING.")
                return
                
            # 1. Initialize services
            knowledge_repo = KnowledgeRepository(self.db)
            document_repo = DocumentRepository(self.db)
            
            retrieval_service = RetrievalService(
                knowledge_repo=knowledge_repo,
                document_repo=document_repo,
                weights=RankingWeights(
                    title=0.3, content=0.1, coverage=0.15, type=0.1, 
                    relationship=0.1, evidence=0.1, passage=0.1, confidence=0.05
                )
            )
            llm_provider = _get_provider(job.config)
            
            planner = ArtifactPlanner(knowledge_repo, retrieval_service, llm_provider)
            validator = ArtifactValidator()
            renderer = PPTXRenderer()
            
            # Resolve effective selection shared across planning and validation
            effective_selection = resolve_effective_selection_for_job(self.db, job)

            # 2. Planning (Phase 9C)
            plan = await planner.plan(ArtifactJobRead.model_validate(job))
            
            # 3. Validation (Phase 9D)
            current_stage = "VALIDATION"
            context = ArtifactValidationContext(
                valid_node_ids=effective_selection.permitted_entity_ids,
                valid_evidence_ids=effective_selection.permitted_evidence_ids,
                expected_units=set(effective_selection.selected_container_ids),
                config=job.config,
                container_type=effective_selection.container_type,
                container_to_descendants=effective_selection.container_to_descendants
            )
            validation_result = validator.validate(plan, context)
            
            if not validation_result.is_valid:
                errors = [f"{e.category}: {e.message}" for e in validation_result.errors]
                raise ValueError(f"Validation failed: {'; '.join(errors)}")
                
            # Persist validated plan and metadata diagnostics
            job.plan = plan.model_dump()
            self.db.commit()

            # 4. Transition to RENDERING
            current_stage = "RENDERING"
            job = self.repo.update_job_status(job_id, ArtifactStatus.RENDERING)
            
            # 5. Rendering (Phase 9B)
            out_dir = Path("data/artifacts")
            out_dir.mkdir(parents=True, exist_ok=True)
            
            result_path = renderer.render(plan, str(out_path))
            
            # 6. Reopen verification: ensure artifact exists and is not corrupt
            current_stage = "VERIFICATION"
            if not os.path.exists(result_path) or os.path.getsize(result_path) == 0:
                raise ValueError(f"Rendered artifact file is missing or empty at {result_path}")
            try:
                prs_check = pptx.Presentation(result_path)
                if len(prs_check.slides) == 0:
                    raise ValueError("Rendered artifact presentation contains zero slides")
            except Exception as pe:
                if os.path.exists(result_path):
                    try:
                        os.remove(result_path)
                    except Exception:
                        pass
                raise ValueError(f"Rendered artifact failed integrity verification: {str(pe)}")

            # 7. COMPLETED
            job.artifact_uri = str(result_path)
            job.status = ArtifactStatus.COMPLETED.value
            job.completed_at = datetime.utcnow()
            self.db.commit()
            
            logger.info(f"Successfully completed artifact job {job_id}")

        except Exception as e:
            logger.error(f"Failed artifact pipeline for {job_id} at stage {current_stage}: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Clean up partial file on failure: do not leave a downloadable partial artifact
            if out_path.exists():
                try:
                    out_path.unlink()
                except Exception:
                    pass

            # Transition to FAILED
            try:
                self.db.rollback()
                job = self.repo.get_job(job_id)
                if job:
                    job.status = ArtifactStatus.FAILED.value
                    job.error_message = f"[{current_stage}] {str(e)}"
                    job.completed_at = datetime.utcnow()
                    job.artifact_uri = None
                    self.db.commit()
            except Exception as inner_e:
                logger.error(f"Failed to save FAILED status for job {job_id}: {str(inner_e)}")
                self.db.rollback()
