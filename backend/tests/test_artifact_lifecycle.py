import unittest
import uuid
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from app.models.document import Base, Document
from app.models.knowledge import KnowledgeVersion
from app.schemas.knowledge import KnowledgeVersionStatus
from app.schemas.artifact import ArtifactJobCreate, ArtifactType, ArtifactStatus
from app.services.artifact.artifact_service import ArtifactService

class TestArtifactLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.SessionLocal()
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

    def test_create_artifact_job_success(self):
        kv = KnowledgeVersion(
            id=str(uuid.uuid4()),
            upload_id=self.upload_id,
            snapshot_id=str(uuid.uuid4()),
            status=KnowledgeVersionStatus.FINALIZED.value
        )
        self.db.add(kv)
        self.db.commit()

        svc = ArtifactService(self.db)
        req = ArtifactJobCreate(
            upload_id=self.upload_id,
            knowledge_version_id=kv.id,
            artifact_type=ArtifactType.PPTX
        )
        
        job = svc.create_artifact_job(req)
        self.assertEqual(job.status, ArtifactStatus.PENDING)

    def test_create_artifact_job_unfinalized_fails(self):
        kv = KnowledgeVersion(
            id=str(uuid.uuid4()),
            upload_id=self.upload_id,
            snapshot_id=str(uuid.uuid4()),
            status=KnowledgeVersionStatus.BUILDING.value
        )
        self.db.add(kv)
        self.db.commit()

        svc = ArtifactService(self.db)
        req = ArtifactJobCreate(
            upload_id=self.upload_id,
            knowledge_version_id=kv.id,
            artifact_type=ArtifactType.PPTX
        )
        
        with self.assertRaises(HTTPException) as cm:
            svc.create_artifact_job(req)
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("unfinalized", cm.exception.detail.lower())

    def test_create_artifact_job_wrong_upload_id_fails(self):
        kv = KnowledgeVersion(
            id=str(uuid.uuid4()),
            upload_id="some-other-upload-id",
            snapshot_id=str(uuid.uuid4()),
            status=KnowledgeVersionStatus.FINALIZED.value
        )
        self.db.add(kv)
        self.db.commit()

        svc = ArtifactService(self.db)
        req = ArtifactJobCreate(
            upload_id=self.upload_id,
            knowledge_version_id=kv.id,
            artifact_type=ArtifactType.PPTX
        )
        
        with self.assertRaises(HTTPException) as cm:
            svc.create_artifact_job(req)
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("does not belong", cm.exception.detail.lower())
