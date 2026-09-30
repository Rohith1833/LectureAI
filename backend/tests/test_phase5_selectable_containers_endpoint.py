import unittest
import uuid
import time
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.session import get_db
from app.models.document import Base, Document
from app.models.review import AcademicGraphSnapshot
from app.models.knowledge import (
    KnowledgeVersion,
    KnowledgeEntity,
    KnowledgeRelationship,
    KnowledgeEvidence
)


def create_test_snapshot(upload_id: str, approval_version: int = 1) -> AcademicGraphSnapshot:
    return AcademicGraphSnapshot(
        id=str(uuid.uuid4()),
        upload_id=upload_id,
        pipeline_run_id=str(uuid.uuid4()),
        approval_version=approval_version,
        approved_revision=1,
        base_graph_fingerprint="bfp_" + str(uuid.uuid4())[:8],
        resolved_graph_fingerprint="rfp_" + str(uuid.uuid4())[:8],
        approval_timestamp=time.time(),
        reviewer_id="test_reviewer",
        nodes=[],
        edges=[]
    )


class TestPhase5SelectableContainersEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
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

    def tearDown(self):
        self.db.close()

    def test_selectable_containers_units_mode(self):
        """Test UNITS mode returns canonically ordered units, page ranges, and no sentinels."""
        upload_id = str(uuid.uuid4())
        doc = Document(
            id=str(uuid.uuid4()),
            upload_id=upload_id,
            status="processed",
            extraction_timestamp=datetime.utcnow(),
            processing_time=0.0
        )
        self.db.add(doc)

        snapshot = create_test_snapshot(upload_id, approval_version=1)
        self.db.add(snapshot)

        kv = KnowledgeVersion(
            id=str(uuid.uuid4()),
            upload_id=upload_id,
            snapshot_id=snapshot.id,
            status="FINALIZED",
            created_at=1700000000.0
        )
        self.db.add(kv)

        # Unit 1 on page 1
        u1 = KnowledgeEntity(
            id=str(uuid.uuid4()),
            knowledge_version_id=kv.id,
            entity_type="UNIT",
            title="Unit 1: Foundations",
            content="Content of unit 1",
            stable_id="anc_unit_1",
            metadata_json={"canonical_source_position": [1, 1], "snapshot_index": 0}
        )
        # Unit 2 on page 30
        u2 = KnowledgeEntity(
            id=str(uuid.uuid4()),
            knowledge_version_id=kv.id,
            entity_type="UNIT",
            title="Unit 2: Advanced Topics",
            content="Content of unit 2",
            stable_id="anc_unit_2",
            metadata_json={"canonical_source_position": [30, 1], "snapshot_index": 1}
        )
        # Topic under Unit 1 on page 5
        top1 = KnowledgeEntity(
            id=str(uuid.uuid4()),
            knowledge_version_id=kv.id,
            entity_type="TOPIC",
            title="Topic 1.1: Basics",
            content="Content",
            stable_id="anc_top_1",
            metadata_json={"canonical_source_position": [5, 1], "snapshot_index": 2}
        )
        self.db.add_all([u1, u2, top1])

        # Relationship: u1 CONTAINS top1
        rel = KnowledgeRelationship(
            id=str(uuid.uuid4()),
            knowledge_version_id=kv.id,
            source_entity_id=u1.id,
            target_entity_id=top1.id,
            relationship_type="CONTAINS",
            confidence=1.0
        )
        self.db.add(rel)

        # Evidence on page 10 for topic 1
        ev = KnowledgeEvidence(
            id=str(uuid.uuid4()),
            entity_id=top1.id,
            document_id=doc.id,
            page_number=10,
            provenance="EXPLICIT"
        )
        self.db.add(ev)
        self.db.commit()

        # Query version endpoint
        resp = self.client.get(f"/api/v1/knowledge/versions/{kv.id}/selectable-containers")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]

        self.assertEqual(data["knowledge_version_id"], kv.id)
        self.assertEqual(data["document_id"], doc.id)
        self.assertEqual(data["upload_id"], upload_id)
        self.assertEqual(data["container_mode"], "UNITS")
        self.assertEqual(data["container_type"], "UNIT")
        self.assertEqual(len(data["containers"]), 2)

        # Order must be Unit 1 first, Unit 2 second
        c1 = data["containers"][0]
        c2 = data["containers"][1]
        self.assertEqual(c1["id"], u1.id)
        self.assertEqual(c1["title"], "Unit 1: Foundations")
        self.assertEqual(c1["source_page_start"], 1)
        self.assertEqual(c1["source_page_end"], 10)  # max page across unit and descendants
        self.assertEqual(c1["topic_count"], 1)

        self.assertEqual(c2["id"], u2.id)
        self.assertEqual(c2["title"], "Unit 2: Advanced Topics")
        self.assertEqual(c2["source_page_start"], 30)

        # Query document endpoint
        doc_resp = self.client.get(f"/api/v1/knowledge/document/{doc.id}/selectable-containers")
        self.assertEqual(doc_resp.status_code, 200)
        self.assertEqual(doc_resp.json()["data"]["knowledge_version_id"], kv.id)

    def test_sentinel_pages_mapped_to_null(self):
        """Ordering sentinels (e.g. 999999999) must never be displayed as real page numbers."""
        upload_id = str(uuid.uuid4())
        doc = Document(
            id=str(uuid.uuid4()),
            upload_id=upload_id,
            status="processed",
            extraction_timestamp=datetime.utcnow(),
            processing_time=0.0
        )
        self.db.add(doc)

        snapshot = create_test_snapshot(upload_id, approval_version=1)
        self.db.add(snapshot)

        kv = KnowledgeVersion(
            id=str(uuid.uuid4()),
            upload_id=upload_id,
            snapshot_id=snapshot.id,
            status="FINALIZED",
            created_at=1700000000.0
        )
        self.db.add(kv)

        # Entity with sentinel position
        u_sentinel = KnowledgeEntity(
            id=str(uuid.uuid4()),
            knowledge_version_id=kv.id,
            entity_type="UNIT",
            title="Unit Without Pages",
            content="Content",
            stable_id="anc_unit_sentinel",
            metadata_json={"canonical_source_position": [999999999, 999999999], "snapshot_index": 0}
        )
        self.db.add(u_sentinel)
        self.db.commit()

        resp = self.client.get(f"/api/v1/knowledge/versions/{kv.id}/selectable-containers")
        self.assertEqual(resp.status_code, 200)
        container = resp.json()["data"]["containers"][0]

        # Sentinel MUST be mapped to null, not 999999999
        self.assertIsNone(container["source_page_start"])
        self.assertIsNone(container["source_page_end"])

    def test_chapters_mode(self):
        """When only CHAPTER entities exist, container_mode is CHAPTERS and actual titles preserved."""
        upload_id = str(uuid.uuid4())
        doc = Document(
            id=str(uuid.uuid4()),
            upload_id=upload_id,
            status="processed",
            extraction_timestamp=datetime.utcnow(),
            processing_time=0.0
        )
        self.db.add(doc)

        snapshot = create_test_snapshot(upload_id, approval_version=1)
        self.db.add(snapshot)

        kv = KnowledgeVersion(
            id=str(uuid.uuid4()),
            upload_id=upload_id,
            snapshot_id=snapshot.id,
            status="FINALIZED",
            created_at=1700000000.0
        )
        self.db.add(kv)

        c1 = KnowledgeEntity(
            id=str(uuid.uuid4()),
            knowledge_version_id=kv.id,
            entity_type="CHAPTER",
            title="Chapter 1: Quantum Mechanics",
            content="Content",
            stable_id="anc_chap_1",
            metadata_json={"canonical_source_position": [1, 1], "snapshot_index": 0}
        )
        self.db.add(c1)
        self.db.commit()

        resp = self.client.get(f"/api/v1/knowledge/versions/{kv.id}/selectable-containers")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]

        self.assertEqual(data["container_mode"], "CHAPTERS")
        self.assertEqual(data["container_type"], "CHAPTER")
        self.assertEqual(len(data["containers"]), 1)
        self.assertEqual(data["containers"][0]["title"], "Chapter 1: Quantum Mechanics")
        self.assertTrue(any("Chapters mode" in d for d in data["diagnostics"]))

    def test_review_required_mode(self):
        """When no units or chapters exist, container_mode is REVIEW_REQUIRED with empty containers."""
        upload_id = str(uuid.uuid4())
        doc = Document(
            id=str(uuid.uuid4()),
            upload_id=upload_id,
            status="processed",
            extraction_timestamp=datetime.utcnow(),
            processing_time=0.0
        )
        self.db.add(doc)

        snapshot = create_test_snapshot(upload_id, approval_version=1)
        self.db.add(snapshot)

        kv = KnowledgeVersion(
            id=str(uuid.uuid4()),
            upload_id=upload_id,
            snapshot_id=snapshot.id,
            status="FINALIZED",
            created_at=1700000000.0
        )
        self.db.add(kv)

        # Only concepts exist
        concept = KnowledgeEntity(
            id=str(uuid.uuid4()),
            knowledge_version_id=kv.id,
            entity_type="CONCEPT",
            title="Isolated Concept",
            content="Content",
            stable_id="anc_concept_1",
            metadata_json={}
        )
        self.db.add(concept)
        self.db.commit()

        resp = self.client.get(f"/api/v1/knowledge/versions/{kv.id}/selectable-containers")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]

        self.assertEqual(data["container_mode"], "REVIEW_REQUIRED")
        self.assertEqual(len(data["containers"]), 0)
        self.assertTrue(len(data["diagnostics"]) > 0)
