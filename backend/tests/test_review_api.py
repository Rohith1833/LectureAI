import os
import unittest
import time
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.session import get_db
from app.models import Base, Document, DocumentBlock, DocumentPage, DocumentMetadata
from app.models.review import AcademicOverride, AcademicAuditEntry
from app.schemas.academic import AcademicNodeCategory
from app.schemas.review import NodeReviewState


class TestReviewAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Create temporary SQLite database file for API integration testing
        cls.db_path = "test_review_api.db"
        cls.engine = create_engine(f"sqlite:///{cls.db_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=cls.engine)
        cls.TestingSessionLocal = sessionmaker(bind=cls.engine)

        # Override dependency injection in FastAPI app
        def override_get_db():
            db = cls.TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.engine.dispose()
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass

    def setUp(self):
        # Establish isolated database records for this test run
        self.db = self.TestingSessionLocal()
        
        # Populate mock Document schema to satisfy base graph extraction
        self.upload_id = f"upload_{uuid_str()}"
        self.doc = Document(
            upload_id=self.upload_id,
            status="processed",
            extraction_timestamp=str(time.time()),
            processing_time=0.1
        )
        self.db.add(self.doc)
        self.db.flush()

        self.meta = DocumentMetadata(
            document_id=self.doc.id,
            page_count=1
        )
        self.db.add(self.meta)

        self.page = DocumentPage(
            document_id=self.doc.id,
            page_number=1,
            width=600.0,
            height=800.0
        )
        self.db.add(self.page)
        self.db.flush()

        # Create two blocks: 1 Chapter heading, 1 Paragraph
        self.ch_block = DocumentBlock(
            id="b_ch1",
            document_id=self.doc.id,
            page_id=self.page.id,
            page_number=1,
            reading_order=0,
            block_type="HEADING",
            text="Chapter 1: Quantum Computing",
            x0=10.0, y0=10.0, x1=200.0, y1=30.0,
            heading_level=1,
            font_family="Arial",
            font_size=18.0,
            bold=True,
            italic=False,
            confidence=1.0,
            provenance="pdfplumber"
        )
        self.def_block = DocumentBlock(
            id="b_def",
            document_id=self.doc.id,
            page_id=self.page.id,
            page_number=1,
            reading_order=1,
            block_type="PARAGRAPH",
            text="Definition 1: A qubit is the basic unit of quantum information.",
            x0=10.0, y0=50.0, x1=500.0, y1=80.0,
            parent_block_id="b_ch1",
            font_family="Arial",
            font_size=10.0,
            bold=False,
            italic=False,
            confidence=0.9,
            provenance="pdfplumber"
        )
        self.db.add(self.ch_block)
        self.db.add(self.def_block)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        # Drop and recreate tables to ensure absolute test isolation
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

    def test_get_review_summary(self):
        """Test GET /api/v1/academic/review/{upload_id} returns correct summary metrics."""
        response = self.client.get(f"/api/v1/academic/review/{self.upload_id}")
        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        self.assertTrue(res_data["success"])
        summary = res_data["data"]
        self.assertEqual(summary["upload_id"], self.upload_id)
        self.assertEqual(summary["total_nodes"], 2)  # Chapter and Definition
        self.assertEqual(summary["unreviewed_count"], 2)
        self.assertEqual(summary["resolved_graph_version"], 0)

    def test_get_resolved_graph_with_filtering(self):
        """Test GET /api/v1/academic/review/{upload_id}/graph filters and paginates nodes."""
        response = self.client.get(
            f"/api/v1/academic/review/{self.upload_id}/graph",
            params={"category": "DEFINITION", "limit": 1, "offset": 0}
        )
        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        self.assertTrue(res_data["success"])
        graph = res_data["data"]
        self.assertEqual(graph["total_count"], 1)
        self.assertEqual(len(graph["nodes"]), 1)
        self.assertEqual(graph["nodes"][0]["category"], "DEFINITION")

    def test_get_node_details(self):
        """Test GET /api/v1/academic/review/{upload_id}/nodes/{node_id} retrieves node context."""
        # Query graph first to retrieve dynamic node ID
        graph_res = self.client.get(f"/api/v1/academic/review/{self.upload_id}/graph")
        self.assertEqual(graph_res.status_code, 200)
        nodes = graph_res.json()["data"]["nodes"]
        def_node = next(n for n in nodes if n["target_block_id"] == "b_def")
        node_id = def_node["node_id"]

        response = self.client.get(f"/api/v1/academic/review/{self.upload_id}/nodes/{node_id}")
        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        self.assertTrue(res_data["success"])
        details = res_data["data"]
        self.assertEqual(details["node_id"], node_id)
        self.assertEqual(details["category"], "DEFINITION")
        self.assertTrue(details["title"].startswith("Definition 1:"))
        self.assertEqual(details["parent_id"], "an_b_ch1")

    def test_apply_action_mutation_and_audit(self):
        """POST /actions successfully writes override and immutable audit entry atomically."""
        # Query graph first to retrieve dynamic anchor key
        graph_res = self.client.get(f"/api/v1/academic/review/{self.upload_id}/graph")
        self.assertEqual(graph_res.status_code, 200)
        nodes = graph_res.json()["data"]["nodes"]
        def_node = next(n for n in nodes if n["target_block_id"] == "b_def")
        anchor_key = def_node["anchor_key"]
        node_id = def_node["node_id"]

        action_payload = {
            "action_type": "CHANGE_CATEGORY",
            "payload": {
                "target_anchor_key": anchor_key,
                "new_category": "THEOREM"
            },
            "expected_version": 0,
            "comment": "Changed qubit definition to theorem category"
        }

        response = self.client.post(
            f"/api/v1/academic/review/{self.upload_id}/actions",
            json=action_payload
        )
        self.assertEqual(response.status_code, 200)
        
        # Verify response structure
        res_data = response.json()
        self.assertTrue(res_data["success"])
        self.assertEqual(res_data["data"]["new_version"], 1)

        # Verify override created in DB
        db_session = self.TestingSessionLocal()
        override = db_session.query(AcademicOverride).filter(AcademicOverride.upload_id == self.upload_id).first()
        self.assertIsNotNone(override)
        self.assertEqual(override.action_type, "CHANGE_CATEGORY")
        self.assertEqual(override.payload, {"target_anchor_key": anchor_key, "new_category": "THEOREM"})

        # Verify audit log created in DB
        audit = db_session.query(AcademicAuditEntry).filter(AcademicAuditEntry.upload_id == self.upload_id).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.action_type, "CHANGE_CATEGORY")
        self.assertEqual(audit.previous_state, {"category": "DEFINITION"})
        self.assertEqual(audit.new_state, {"category": "THEOREM"})
        self.assertEqual(audit.comment, "Changed qubit definition to theorem category")
        db_session.close()

    def test_optimistic_concurrency_control_conflict(self):
        """Ensure OCC raises HTTP 409 Conflict when expected version count mismatches."""
        # Query graph first to retrieve dynamic anchor key
        graph_res = self.client.get(f"/api/v1/academic/review/{self.upload_id}/graph")
        self.assertEqual(graph_res.status_code, 200)
        nodes = graph_res.json()["data"]["nodes"]
        ch_node = next(n for n in nodes if n["target_block_id"] == "b_ch1")
        anchor_key = ch_node["anchor_key"]

        action1 = {
            "action_type": "ACCEPT_NODE",
            "payload": {"target_anchor_key": anchor_key},
            "expected_version": 0
        }
        action2 = {
            "action_type": "RENAME_TITLE",
            "payload": {"target_anchor_key": anchor_key, "new_title": "Quantum Physics"},
            "expected_version": 0  # Stale: expecting version 0, but action1 will increment to 1
        }

        # User A commits successfully (version moves to 1)
        res1 = self.client.post(f"/api/v1/academic/review/{self.upload_id}/actions", json=action1)
        self.assertEqual(res1.status_code, 200)

        # User B attempts to commit with stale version 0
        res2 = self.client.post(f"/api/v1/academic/review/{self.upload_id}/actions", json=action2)
        self.assertEqual(res2.status_code, 409)
        self.assertIn("message", res2.json())
        self.assertIn("Concurrency Control conflict", res2.json()["message"])

    def test_get_reconciliation_listings(self):
        """Verify reconciliation API retrieves list of warnings/conflicts."""
        response = self.client.get(f"/api/v1/academic/review/{self.upload_id}/reconciliation")
        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        self.assertTrue(res_data["success"])
        recon = res_data["data"]
        self.assertEqual(recon["reconciliation_status"], "CLEAN")

    def test_get_audit_history_paginated(self):
        """Verify get audit log lists paginated entries."""
        # Inject manual audit logs
        db_session = self.TestingSessionLocal()
        for i in range(5):
            audit = AcademicAuditEntry(
                upload_id=self.upload_id,
                user_id="user_admin",
                action_type="ACCEPT_NODE",
                node_id=f"node_{i}",
                previous_state={},
                new_state={},
                comment=f"Log {i}"
            )
            db_session.add(audit)
        db_session.commit()
        db_session.close()

        response = self.client.get(
            f"/api/v1/academic/review/{self.upload_id}/audit",
            params={"limit": 2, "offset": 1}
        )
        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        self.assertTrue(res_data["success"])
        audit_data = res_data["data"]
        self.assertEqual(audit_data["total_count"], 5)
        self.assertEqual(len(audit_data["audits"]), 2)
        self.assertEqual(audit_data["audits"][0]["comment"], "Log 1")

    def test_revision_increments_and_remains_monotone(self):
        """Verify revision starts at 0, increments by 1 on success, does not change on failure, and never decreases."""
        # 1. Start check
        sum_res = self.client.get(f"/api/v1/academic/review/{self.upload_id}")
        self.assertEqual(sum_res.json()["data"]["resolved_graph_version"], 0)

        # Query dynamic anchor
        graph_res = self.client.get(f"/api/v1/academic/review/{self.upload_id}/graph")
        anchor_key = graph_res.json()["data"]["nodes"][0]["anchor_key"]

        # 2. Apply success mutation
        action_payload = {
            "action_type": "ACCEPT_NODE",
            "payload": {"target_anchor_key": anchor_key},
            "expected_version": 0
        }
        res1 = self.client.post(f"/api/v1/academic/review/{self.upload_id}/actions", json=action_payload)
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json()["data"]["new_version"], 1)

        # 3. Apply failed mutation (OCC mismatch)
        failed_payload = {
            "action_type": "ACCEPT_NODE",
            "payload": {"target_anchor_key": anchor_key},
            "expected_version": 0  # Expected is stale (current is 1)
        }
        res2 = self.client.post(f"/api/v1/academic/review/{self.upload_id}/actions", json=failed_payload)
        self.assertEqual(res2.status_code, 409)

        # Verify revision remains at 1
        sum_res2 = self.client.get(f"/api/v1/academic/review/{self.upload_id}")
        self.assertEqual(sum_res2.json()["data"]["resolved_graph_version"], 1)

    def test_inactive_overrides_do_not_decrease_revision(self):
        """Verify making an override inactive (or deleting it) does not decrease the monotonic version revision."""
        # 1. Apply mutation to move to revision 1
        graph_res = self.client.get(f"/api/v1/academic/review/{self.upload_id}/graph")
        anchor_key = graph_res.json()["data"]["nodes"][0]["anchor_key"]

        action = {
            "action_type": "ACCEPT_NODE",
            "payload": {"target_anchor_key": anchor_key},
            "expected_version": 0
        }
        res1 = self.client.post(f"/api/v1/academic/review/{self.upload_id}/actions", json=action)
        self.assertEqual(res1.status_code, 200)

        # 2. Manually deactivate override in database
        db_session = self.TestingSessionLocal()
        override = db_session.query(AcademicOverride).filter(AcademicOverride.upload_id == self.upload_id).first()
        override.is_active = False
        db_session.commit()
        db_session.close()

        # 3. Verify revision is still 1 (has not decreased to 0 despite 0 active overrides)
        sum_res = self.client.get(f"/api/v1/academic/review/{self.upload_id}")
        self.assertEqual(sum_res.json()["data"]["resolved_graph_version"], 1)

    def test_concurrent_request_concurrency_failure(self):
        """Simulate two concurrent clients sending expected_version=0: only one succeeds, the other aborts with 409 and leaves DB unmutated."""
        graph_res = self.client.get(f"/api/v1/academic/review/{self.upload_id}/graph")
        anchor_key = graph_res.json()["data"]["nodes"][0]["anchor_key"]

        action1 = {
            "action_type": "RENAME_TITLE",
            "payload": {"target_anchor_key": anchor_key, "new_title": "Title A"},
            "expected_version": 0
        }
        action2 = {
            "action_type": "RENAME_TITLE",
            "payload": {"target_anchor_key": anchor_key, "new_title": "Title B"},
            "expected_version": 0
        }

        # Client 1 succeeds
        res1 = self.client.post(f"/api/v1/academic/review/{self.upload_id}/actions", json=action1)
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json()["data"]["new_version"], 1)

        # Client 2 fails (OCC mismatch)
        res2 = self.client.post(f"/api/v1/academic/review/{self.upload_id}/actions", json=action2)
        self.assertEqual(res2.status_code, 409)

        # Check DB states: only 1 override and 1 audit log should exist
        db_session = self.TestingSessionLocal()
        overrides = db_session.query(AcademicOverride).filter(AcademicOverride.upload_id == self.upload_id).all()
        audits = db_session.query(AcademicAuditEntry).filter(AcademicAuditEntry.upload_id == self.upload_id).all()
        
        self.assertEqual(len(overrides), 1)
        self.assertEqual(len(audits), 1)
        self.assertEqual(overrides[0].payload["new_title"], "Title A")
        db_session.close()

    def test_base_graph_caching_performance(self):
        """Regression test: verify that the compiled base graph is cached and subsequent loads are near-instant."""
        from app.services.intelligence.review.service import _BASE_GRAPH_CACHE
        
        # Clear cache for this upload if exists
        if self.upload_id in _BASE_GRAPH_CACHE:
            del _BASE_GRAPH_CACHE[self.upload_id]
            
        # First load (should run pipeline and populate cache)
        t0 = time.time()
        res1 = self.client.get(f"/api/v1/academic/review/{self.upload_id}/graph")
        t1 = time.time()
        self.assertEqual(res1.status_code, 200)
        first_load_duration = t1 - t0
        
        # Verify cached
        cache_key = f"{self.upload_id}:{self.doc.extraction_timestamp}"
        self.assertIn(cache_key, _BASE_GRAPH_CACHE)
        
        # Second load (should hit cache)
        t2 = time.time()
        res2 = self.client.get(f"/api/v1/academic/review/{self.upload_id}/graph")
        t3 = time.time()
        self.assertEqual(res2.status_code, 200)
        second_load_duration = t3 - t2
        
        # Caching should be significantly faster (under 50ms)
        self.assertLess(second_load_duration, 0.05)




def uuid_str() -> str:
    import uuid
    return str(uuid.uuid4())


if __name__ == "__main__":
    unittest.main()
