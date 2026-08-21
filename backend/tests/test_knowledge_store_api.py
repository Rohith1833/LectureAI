import os
import unittest
import time
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.session import get_db
from app.models import Base, Document, AcademicGraphSnapshot, DocumentBlock, DocumentPage
from app.models.knowledge import KnowledgeVersion, KnowledgeEntity, KnowledgeRelationship, KnowledgeEvidence
from app.schemas.knowledge import KnowledgeRelationshipType, KnowledgeEvidenceProvenance

class TestKnowledgeStoreAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.db_path = "test_knowledge_store_api.db"
        cls.engine = create_engine(
            f"sqlite:///{cls.db_path}",
            connect_args={"check_same_thread": False}
        )

        @event.listens_for(cls.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(bind=cls.engine)
        cls.TestingSessionLocal = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.TestingSessionLocal()

        # Override FastAPI dependency to use test database
        def override_get_db():
            try:
                yield self.db
            finally:
                pass
        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

        # 1. Setup Document in APPROVED state
        self.upload_id = str(uuid.uuid4())
        self.doc = Document(
            upload_id=self.upload_id,
            status="processed",
            extraction_timestamp="2026-08-21T12:00:00Z",
            processing_time=1.0,
            review_state="APPROVED"
        )
        self.db.add(self.doc)
        self.db.flush()

        self.page = DocumentPage(
            document_id=self.doc.id,
            page_number=1,
            width=612.0,
            height=792.0
        )
        self.db.add(self.page)
        self.db.flush()

        self.block_id = "blk_1"
        self.block = DocumentBlock(
            id=self.block_id,
            document_id=self.doc.id,
            page_id=self.page.id,
            page_number=1,
            reading_order=1,
            block_type="PARAGRAPH",
            text="Core concepts.",
            x0=10.0, y0=20.0, x1=110.0, y1=120.0,
            provenance="PEDAGOGICAL_CLASSIFICATION_MODULE"
        )
        self.db.add(self.block)
        self.db.flush()

        # 2. Seed snapshots (snapshot 1 = older, snapshot 2 = latest by approval_version)
        self.snapshot1 = AcademicGraphSnapshot(
            id=str(uuid.uuid4()),
            upload_id=self.upload_id,
            pipeline_run_id="run_1",
            approval_version=1,
            approved_revision=2,
            base_graph_fingerprint="bfp1",
            resolved_graph_fingerprint="rfp1",
            approval_timestamp=time.time() - 100,
            reviewer_id="reviewer_1",
            nodes=[], edges=[]
        )
        self.snapshot2 = AcademicGraphSnapshot(
            id=str(uuid.uuid4()),
            upload_id=self.upload_id,
            pipeline_run_id="run_2",
            approval_version=2,
            approved_revision=4,
            base_graph_fingerprint="bfp2",
            resolved_graph_fingerprint="rfp2",
            approval_timestamp=time.time(),
            reviewer_id="reviewer_1",
            nodes=[], edges=[]
        )
        self.snapshot_building = AcademicGraphSnapshot(
            id=str(uuid.uuid4()),
            upload_id=self.upload_id,
            pipeline_run_id="run_building",
            approval_version=3,
            approved_revision=5,
            base_graph_fingerprint="bfp_building",
            resolved_graph_fingerprint="rfp_building",
            approval_timestamp=time.time(),
            reviewer_id="reviewer_1",
            nodes=[], edges=[]
        )
        self.db.add_all([self.snapshot1, self.snapshot2, self.snapshot_building])
        self.db.commit()

        # 3. Seed versions corresponding to snapshots (status=BUILDING first to allow entity addition)
        self.v1 = KnowledgeVersion(
            id=str(uuid.uuid4()),
            upload_id=self.upload_id,
            snapshot_id=self.snapshot1.id,
            schema_version="1.0.0",
            created_at=time.time() - 100,
            status="BUILDING",
            metadata_json={"reviewer_id": "reviewer_1"}
        )
        self.v2 = KnowledgeVersion(
            id=str(uuid.uuid4()),
            upload_id=self.upload_id,
            snapshot_id=self.snapshot2.id,
            schema_version="1.0.0",
            created_at=time.time(),
            status="BUILDING",
            metadata_json={"reviewer_id": "reviewer_1"}
        )
        # Also seed a building (incomplete) version to test isolation
        self.v_building = KnowledgeVersion(
            id=str(uuid.uuid4()),
            upload_id=self.upload_id,
            snapshot_id=self.snapshot_building.id,
            schema_version="1.0.0",
            created_at=time.time() + 10,
            status="BUILDING",
            metadata_json={}
        )
        self.db.add_all([self.v1, self.v2, self.v_building])
        self.db.flush()

        # 4. Seed Entities, Relationships, and Evidence under v2 while status is BUILDING
        self.e1 = KnowledgeEntity(
            id=str(uuid.uuid4()),
            knowledge_version_id=self.v2.id,
            entity_type="CONCEPT",
            title="Quantum Entanglement",
            content="Quantum Entanglement content",
            stable_id="anc_quantum_entanglement",
            metadata_json={}
        )
        self.e2 = KnowledgeEntity(
            id=str(uuid.uuid4()),
            knowledge_version_id=self.v2.id,
            entity_type="DEFINITION",
            title="Entanglement Definition",
            content="Definition content",
            stable_id="anc_entanglement_def",
            metadata_json={}
        )
        self.db.add_all([self.e1, self.e2])
        self.db.flush()

        self.rel1 = KnowledgeRelationship(
            id=str(uuid.uuid4()),
            knowledge_version_id=self.v2.id,
            source_entity_id=self.e1.id,
            target_entity_id=self.e2.id,
            relationship_type="CONTAINS",
            confidence=0.99,
            is_inferred=False,
            is_human_confirmed=True,
            metadata_json={}
        )
        self.db.add(self.rel1)

        # Evidence with block (page_number = 1)
        self.ev1 = KnowledgeEvidence(
            id=str(uuid.uuid4()),
            entity_id=self.e1.id,
            document_id=self.doc.id,
            page_number=1,
            section_title="Intro",
            source_node_id="node_1",
            source_anchor_key="anc_quantum_entanglement",
            text_reference="Core concepts.",
            provenance="EXPLICIT_CLASSIFIER",
            x0=10.0, y0=20.0, x1=110.0, y1=120.0
        )
        # Evidence without block (page_number = null/None)
        self.ev_null = KnowledgeEvidence(
            id=str(uuid.uuid4()),
            entity_id=self.e2.id,
            document_id=self.doc.id,
            page_number=None,
            section_title=None,
            source_node_id="node_2",
            source_anchor_key="anc_entanglement_def",
            text_reference=None,
            provenance="UNKNOWN",
            x0=None, y0=None, x1=None, y1=None
        )
        self.db.add_all([self.ev1, self.ev_null])
        self.db.flush()

        # 5. Finalize the target versions
        self.v1.status = "FINALIZED"
        self.v2.status = "FINALIZED"
        self.db.commit()

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def test_01_get_latest_finalized_version(self):
        """Verify endpoint returns the latest version mapped to snapshot version desc."""
        response = self.client.get(f"/api/v1/knowledge/document/{self.doc.id}")
        self.assertEqual(response.status_code, 200)
        res_json = response.json()
        self.assertTrue(res_json["success"])
        # Should resolve to v2 (associated with approval_version=2 snapshot)
        self.assertEqual(res_json["data"]["id"], self.v2.id)
        self.assertEqual(res_json["data"]["document_id"], self.doc.id)
        self.assertEqual(res_json["data"]["upload_id"], self.upload_id)
        self.assertEqual(res_json["data"]["entity_count"], 2)
        self.assertEqual(res_json["data"]["relationship_count"], 1)
        self.assertEqual(res_json["data"]["evidence_count"], 2)
        self.assertEqual(res_json["data"]["approval_version"], 2)

    def test_02_list_finalized_versions(self):
        """Verify list endpoint retrieves only finalized runs."""
        response = self.client.get(f"/api/v1/knowledge/document/{self.doc.id}/versions")
        self.assertEqual(response.status_code, 200)
        res_json = response.json()
        # Should return v2 and v1, excluding v_building (which is BUILDING)
        versions = res_json["data"]
        self.assertEqual(len(versions), 2)
        version_ids = [v["id"] for v in versions]
        self.assertIn(self.v1.id, version_ids)
        self.assertIn(self.v2.id, version_ids)
        self.assertNotIn(self.v_building.id, version_ids)

    def test_03_get_version_by_id_building_hidden(self):
        """Verify requesting a BUILDING version returns 404."""
        response = self.client.get(f"/api/v1/knowledge/versions/{self.v_building.id}")
        self.assertEqual(response.status_code, 404)

    def test_04_list_entities_pagination_and_filtering(self):
        """Verify entities pagination parameters and category filtering."""
        # Test pagination
        response = self.client.get(f"/api/v1/knowledge/versions/{self.v2.id}/entities?limit=1&offset=0")
        self.assertEqual(response.status_code, 200)
        res_json = response.json()
        self.assertEqual(res_json["data"]["total"], 2)
        self.assertEqual(len(res_json["data"]["items"]), 1)

        # Test filtering by entity_type
        response = self.client.get(f"/api/v1/knowledge/versions/{self.v2.id}/entities?entity_type=CONCEPT")
        self.assertEqual(response.status_code, 200)
        res_json = response.json()
        self.assertEqual(res_json["data"]["total"], 1)
        self.assertEqual(res_json["data"]["items"][0]["id"], self.e1.id)

    def test_05_get_entity_and_evidence(self):
        """Verify retrieving details of a single entity and its evidence."""
        # Retrieve single entity
        response = self.client.get(f"/api/v1/knowledge/versions/{self.v2.id}/entities/{self.e1.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["title"], "Quantum Entanglement")

        # Retrieve evidence
        response = self.client.get(f"/api/v1/knowledge/versions/{self.v2.id}/entities/{self.e1.id}/evidence")
        self.assertEqual(response.status_code, 200)
        ev_items = response.json()["data"]
        self.assertEqual(len(ev_items), 1)
        self.assertEqual(ev_items[0]["page_number"], 1)
        self.assertEqual(ev_items[0]["x0"], 10.0)

    def test_06_evidence_nullable_page_number(self):
        """Verify that unknown/stale evidence returns page_number: null."""
        response = self.client.get(f"/api/v1/knowledge/versions/{self.v2.id}/entities/{self.e2.id}/evidence")
        self.assertEqual(response.status_code, 200)
        ev_items = response.json()["data"]
        self.assertEqual(len(ev_items), 1)
        self.assertIsNone(ev_items[0]["page_number"])
        self.assertIsNone(ev_items[0]["x0"])
        self.assertEqual(ev_items[0]["provenance"], "UNKNOWN")

    def test_07_list_relationships_and_entity_specific_traversal(self):
        """Verify relationships listing and outbound/inbound separations."""
        # Outbound/inbound specific
        response = self.client.get(f"/api/v1/knowledge/versions/{self.v2.id}/entities/{self.e1.id}/relationships")
        self.assertEqual(response.status_code, 200)
        res_json = response.json()
        incoming = res_json["data"]["incoming"]
        outgoing = res_json["data"]["outgoing"]
        
        # e1 (Quantum Entanglement) is the source, so it has 1 outgoing relationship to e2, and 0 incoming
        self.assertEqual(len(incoming), 0)
        self.assertEqual(len(outgoing), 1)
        self.assertEqual(outgoing[0]["target_entity_id"], self.e2.id)

    def test_08_read_only_constraints(self):
        """Verify POST, PUT, DELETE operations on knowledge endpoints return 405 Method Not Allowed."""
        for method in ["post", "put", "delete"]:
            call_func = getattr(self.client, method)
            response = call_func(f"/api/v1/knowledge/versions/{self.v2.id}")
            self.assertEqual(response.status_code, 405)

if __name__ == "__main__":
    unittest.main()
