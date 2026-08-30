import unittest
import uuid
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.models.document import Base, Document
from app.models.knowledge import KnowledgeVersion
from app.schemas.knowledge import KnowledgeVersionStatus
from app.models.artifact import ArtifactJob
from app.schemas.artifact import ArtifactJobCreate, ArtifactType, ArtifactStatus
from app.repositories.artifact_repository import ArtifactRepository

class TestArtifactPersistence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.SessionLocal()
        
        # Create a sample document
        self.upload_id = str(uuid.uuid4())
        doc = Document(
            upload_id=self.upload_id, 
            status="processed",
            extraction_timestamp=datetime.utcnow(),
            processing_time=0.0
        )
        self.db.add(doc)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)

    def test_create_and_retrieve_artifact_job(self):
        # Create a knowledge version
        kv = KnowledgeVersion(
            id=str(uuid.uuid4()),
            upload_id=self.upload_id,
            snapshot_id=str(uuid.uuid4()),
            status=KnowledgeVersionStatus.FINALIZED.value
        )
        self.db.add(kv)
        self.db.commit()

        repo = ArtifactRepository(self.db)
        
        create_data = ArtifactJobCreate(
            upload_id=self.upload_id,
            knowledge_version_id=kv.id,
            artifact_type=ArtifactType.PPTX,
            config={"depth": "high", "include_examples": True}
        )
        job = repo.create_job(create_data)
        self.assertIsNotNone(job.id)
        self.assertEqual(job.status, ArtifactStatus.PENDING.value)
        
        fetched_job = repo.get_job(job.id)
        self.assertIsNotNone(fetched_job)
        self.assertEqual(fetched_job.upload_id, self.upload_id)
        self.assertEqual(fetched_job.config["depth"], "high")

    def test_update_artifact_status(self):
        kv = KnowledgeVersion(
            id=str(uuid.uuid4()),
            upload_id=self.upload_id,
            snapshot_id=str(uuid.uuid4()),
            status=KnowledgeVersionStatus.FINALIZED.value
        )
        self.db.add(kv)
        self.db.commit()

        repo = ArtifactRepository(self.db)
        job = repo.create_job(ArtifactJobCreate(
            upload_id=self.upload_id,
            knowledge_version_id=kv.id,
            artifact_type=ArtifactType.PPTX,
            config={}
        ))
        
        # Update status to PLANNING
        repo.update_job_status(job.id, ArtifactStatus.PLANNING)
        fetched_job = repo.get_job(job.id)
        self.assertEqual(fetched_job.status, ArtifactStatus.PLANNING.value)
        self.assertIsNone(fetched_job.completed_at)
        
        # Update to FAILED
        repo.update_job_status(job.id, ArtifactStatus.FAILED, error_message="Test Error")
        fetched_job = repo.get_job(job.id)
        self.assertEqual(fetched_job.status, ArtifactStatus.FAILED.value)
        self.assertEqual(fetched_job.error_message, "Test Error")
        self.assertIsNotNone(fetched_job.completed_at)

    def test_invalid_state_transitions(self):
        kv = KnowledgeVersion(
            id=str(uuid.uuid4()),
            upload_id=self.upload_id,
            snapshot_id=str(uuid.uuid4()),
            status=KnowledgeVersionStatus.FINALIZED.value
        )
        self.db.add(kv)
        self.db.commit()

        repo = ArtifactRepository(self.db)
        job = repo.create_job(ArtifactJobCreate(
            upload_id=self.upload_id,
            knowledge_version_id=kv.id,
            artifact_type=ArtifactType.PPTX
        ))
        
        # PENDING -> RENDERING is invalid
        with self.assertRaises(ValueError):
            repo.update_job_status(job.id, ArtifactStatus.RENDERING)
            
        # PENDING -> COMPLETED is invalid
        with self.assertRaises(ValueError):
            repo.update_job_status(job.id, ArtifactStatus.COMPLETED)
            
        repo.update_job_status(job.id, ArtifactStatus.PLANNING)
        
        # PLANNING -> COMPLETED is invalid
        with self.assertRaises(ValueError):
            repo.update_job_status(job.id, ArtifactStatus.COMPLETED)
            
        repo.update_job_status(job.id, ArtifactStatus.RENDERING)
        repo.update_job_status(job.id, ArtifactStatus.COMPLETED)
        
        # COMPLETED -> PLANNING is invalid
        with self.assertRaises(ValueError):
            repo.update_job_status(job.id, ArtifactStatus.PLANNING)

    def test_schema_defaults(self):
        from app.schemas.artifact import SlideModel, ArtifactPlan, ArtifactJobCreate
        
        slide = SlideModel(slide_type="CONTENT", title="Test")
        self.assertEqual(slide.content, [])
        self.assertEqual(slide.source_node_ids, [])
        self.assertEqual(slide.evidence_ids, [])
        
        # Verify it's not a shared mutable default
        slide.content.append("test")
        slide2 = SlideModel(slide_type="CONTENT", title="Test 2")
        self.assertEqual(slide2.content, [])
        
        plan = ArtifactPlan()
        self.assertEqual(plan.slides, [])
        
        job_create = ArtifactJobCreate(
            upload_id="123",
            knowledge_version_id="456",
            artifact_type=ArtifactType.PPTX
        )
        self.assertEqual(job_create.config, {})
        job_create.config["test"] = True
        job_create2 = ArtifactJobCreate(
            upload_id="123",
            knowledge_version_id="456",
            artifact_type=ArtifactType.PPTX
        )
        self.assertEqual(job_create2.config, {})


