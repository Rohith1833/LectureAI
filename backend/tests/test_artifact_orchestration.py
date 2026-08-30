import pytest
from unittest.mock import patch, AsyncMock
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker, Session
from app.models.document import Base
from app.models.knowledge import KnowledgeVersion, KnowledgeEntity
from app.schemas.knowledge import KnowledgeVersionStatus
from app.schemas.artifact import ArtifactJobCreate, ArtifactType, ArtifactStatus
from app.schemas.artifact import ArtifactPlan, SlideModel, SlideType
from app.repositories.artifact_repository import ArtifactRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.artifact.artifact_service import ArtifactService

@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

@pytest.fixture
def mock_plan():
    return ArtifactPlan(slides=[
        SlideModel(
            slide_type=SlideType.TITLE,
            title="Test Title",
            content=[],
            source_node_ids=[],
            evidence_ids=[]
        ),
        SlideModel(
            slide_type=SlideType.CONTENT,
            title="Test Content",
            content=["Point 1"],
            source_node_ids=["unit_test"],
            evidence_ids=[]
        )
    ])

@pytest.mark.asyncio
async def test_generation_pipeline_success(db: Session, mock_plan):
    # Setup test data
    k_repo = KnowledgeRepository(db)
    
    # We need a finalized knowledge version with a unit matching 'unit_test'
    # For integration testing, it's easier to create the raw entity and version
    version = KnowledgeVersion(
        id="test_kv_id",
        upload_id="test_upload",
        snapshot_id="test_snapshot",
        status=KnowledgeVersionStatus.FINALIZED.value,
        entities=[KnowledgeEntity(
            id="unit_test",
            entity_type="UNIT",
            title="Unit Test",
            content="Test content",
            stable_id="stable_unit_test",
            metadata_json={},
        )],
        relationships=[]
    )
    db.add(version)
    db.commit()

    repo = ArtifactRepository(db)
    job = repo.create_job(ArtifactJobCreate(
        upload_id="test_upload",
        knowledge_version_id="test_kv_id",
        artifact_type=ArtifactType.PPTX,
        config={"num_units": 1}
    ))
    
    service = ArtifactService(db)

    # Patch the planner to return our mock plan
    with patch("app.services.artifact.artifact_planner.ArtifactPlanner.plan", new_callable=AsyncMock) as mock_plan_method:
        mock_plan_method.return_value = mock_plan
        
        await service.run_generation_pipeline(job.id)
        
    # Verify success
    updated_job = repo.get_job(job.id)
    assert updated_job.status == ArtifactStatus.COMPLETED
    assert updated_job.artifact_uri is not None
    assert Path(updated_job.artifact_uri).exists()
    
    # Cleanup file
    Path(updated_job.artifact_uri).unlink()

@pytest.mark.asyncio
async def test_generation_pipeline_validation_failure(db: Session, mock_plan):
    # Setup test data without the required unit to trigger validation failure
    version = KnowledgeVersion(
        id="test_kv_id_fail",
        upload_id="test_upload_fail",
        snapshot_id="test_snapshot_fail",
        status=KnowledgeVersionStatus.FINALIZED.value,
        entities=[], # Missing 'unit_test' which the mock_plan references
        relationships=[]
    )
    db.add(version)
    db.commit()

    repo = ArtifactRepository(db)
    job = repo.create_job(ArtifactJobCreate(
        upload_id="test_upload_fail",
        knowledge_version_id="test_kv_id_fail",
        artifact_type=ArtifactType.PPTX,
        config={}
    ))
    
    service = ArtifactService(db)

    # Patch the planner to return our mock plan
    with patch("app.services.artifact.artifact_planner.ArtifactPlanner.plan", new_callable=AsyncMock) as mock_plan_method:
        mock_plan_method.return_value = mock_plan
        
        with patch("app.services.artifact.pptx_renderer.PPTXRenderer.render") as mock_renderer:
            await service.run_generation_pipeline(job.id)
            
            # Ensure renderer is NEVER called if validation fails
            mock_renderer.assert_not_called()
        
    # Verify failure
    updated_job = repo.get_job(job.id)
    assert updated_job.status == ArtifactStatus.FAILED
    assert updated_job.artifact_uri is None
    assert "Validation failed" in updated_job.error_message
