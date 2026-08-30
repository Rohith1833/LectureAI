import unittest
import uuid
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.session import get_db
from app.models.document import Base, Document
from app.models.knowledge import KnowledgeVersion
from app.schemas.knowledge import KnowledgeVersionStatus

class TestArtifactAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine)

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()
        
        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.pop(get_db, None)

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

    def test_generate_artifact_api(self):
        kv = KnowledgeVersion(
            id=str(uuid.uuid4()),
            upload_id=self.upload_id,
            snapshot_id=str(uuid.uuid4()),
            status=KnowledgeVersionStatus.FINALIZED.value
        )
        self.db.add(kv)
        self.db.commit()

        response = self.client.post("/api/v1/artifacts/generate", json={
            "upload_id": self.upload_id,
            "knowledge_version_id": kv.id,
            "artifact_type": "PPTX",
            "config": {"audience": "advanced"}
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "PENDING")
        self.assertIn("id", data)
        
        job_id = data["id"]
        
        # Poll status
        poll_res = self.client.get(f"/api/v1/artifacts/{job_id}")
        self.assertEqual(poll_res.status_code, 200)
        poll_data = poll_res.json()
        self.assertEqual(poll_data["id"], job_id)
        self.assertEqual(poll_data["status"], "PENDING")
        
        # List jobs
        list_res = self.client.get(f"/api/v1/artifacts/jobs/{self.upload_id}")
        self.assertEqual(list_res.status_code, 200)
        self.assertGreaterEqual(len(list_res.json()), 1)
