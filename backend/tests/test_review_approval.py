import os
import uuid as _uuid
import unittest
import time
import uuid
from fastapi.testclient import TestClient
from fastapi.exceptions import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from app.main import app
from app.db.session import get_db
from app.models import Base, Document, DocumentBlock, DocumentPage, DocumentMetadata
from app.models.review import AcademicOverride, AcademicAuditEntry, AcademicReviewRevision, AcademicGraphSnapshot
from app.services.intelligence.review.service import AcademicReviewService
from app.schemas.review import NodeReviewState, DocumentReviewState


class TestReviewApproval(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.db_path = "test_review_approval.db"
        cls.engine = create_engine(
            f"sqlite:///{cls.db_path}",
            connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(bind=cls.engine)
        cls.TestingSessionLocal = sessionmaker(bind=cls.engine)

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
        # Clear module-level cache to prevent cross-test pollution
        from app.services.intelligence.review import service as review_svc
        review_svc._BASE_GRAPH_CACHE.clear()

        # Drop and recreate for full isolation
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.TestingSessionLocal()

        self.upload_id = str(_uuid.uuid4())
        self.doc = Document(
            upload_id=self.upload_id,
            status="processed",
            extraction_timestamp="2026-08-20T12:00:00Z",
            processing_time=1.5,
            review_state="NEEDS_REVIEW"
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

        block_id = str(_uuid.uuid4())
        self.block = DocumentBlock(
            id=block_id,
            document_id=self.doc.id,
            page_id=self.page.id,
            page_number=1,
            reading_order=1,
            block_type="HEADING",
            text="Quantum Decoherence: A Chapter Overview",
            heading_level=1,
            x0=10.0, y0=10.0, x1=200.0, y1=30.0,
            font_size=18.0, font_family="Arial",
            bold=True, italic=False, confidence=1.0,
            provenance="pdfplumber"
        )
        self.db.add(self.block)

        block_id2 = str(_uuid.uuid4())
        self.block2 = DocumentBlock(
            id=block_id2,
            document_id=self.doc.id,
            page_id=self.page.id,
            page_number=1,
            reading_order=2,
            block_type="PARAGRAPH",
            text="Definition 1: Quantum decoherence is the process by which quantum information is lost.",
            parent_block_id=block_id,
            x0=10.0, y0=50.0, x1=500.0, y1=80.0,
            font_size=10.0, font_family="Arial",
            bold=False, italic=False, confidence=0.9,
            provenance="pdfplumber"
        )
        self.db.add(self.block2)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _accept_all_nodes(self, service: AcademicReviewService) -> int:
        """Helper: accept all base graph nodes, returns the final revision after all accepts."""
        base_nodes, _ = service.get_base_graph(self.upload_id)
        current_rev = service.review_repo.get_or_create_revision(self.upload_id)
        for node in base_nodes:
            service.apply_review_action(
                upload_id=self.upload_id,
                action_type="ACCEPT_NODE",
                payload={"target_anchor_key": node.anchor_key},
                expected_version=current_rev,
                user_id="reviewer"
            )
            current_rev += 1
        return current_rev

    # ─────────────────────────────────────────────────────────────────────────
    # APPROVAL READINESS TESTS
    # ─────────────────────────────────────────────────────────────────────────

    def test_01_approval_readiness_blocked_by_unreviewed_nodes(self):
        """check_approval_readiness blocks when unreviewed nodes exist."""
        service = AcademicReviewService(self.db)
        readiness = service.check_approval_readiness(self.upload_id)
        self.assertFalse(readiness["eligible"])
        unreviewed_check = next(
            (c for c in readiness["checks"] if c["code"] == "UNREVIEWED_NODES"), None
        )
        self.assertIsNotNone(unreviewed_check)
        self.assertFalse(unreviewed_check["passed"])
        self.assertEqual(unreviewed_check["severity"], "BLOCKER")

    def test_02_approval_readiness_eligible_when_fully_reviewed(self):
        """check_approval_readiness returns eligible=True when all nodes are accepted."""
        service = AcademicReviewService(self.db)
        self._accept_all_nodes(service)
        readiness = service.check_approval_readiness(self.upload_id)
        self.assertTrue(readiness["eligible"])
        self.assertEqual(len(readiness["blocking_reasons"]), 0)

    # ─────────────────────────────────────────────────────────────────────────
    # APPROVAL TRANSACTION TESTS
    # ─────────────────────────────────────────────────────────────────────────

    def test_03_successful_approval_creates_snapshot_and_advances_revision(self):
        """approve_resolved_graph creates snapshot, marks APPROVED, increments revision."""
        service = AcademicReviewService(self.db)
        rev_after_accept = self._accept_all_nodes(service)

        result = service.approve_resolved_graph(
            upload_id=self.upload_id,
            expected_revision=rev_after_accept,
            user_id="reviewer"
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["approval_version"], "v1")
        self.assertEqual(result["approved_revision"], rev_after_accept)

        self.db.expire_all()
        doc = self.db.query(Document).filter(Document.upload_id == self.upload_id).first()
        self.assertEqual(doc.review_state, "APPROVED")

        new_rev = service.review_repo.get_or_create_revision(self.upload_id)
        self.assertEqual(new_rev, rev_after_accept + 1)

        snapshot = service.review_repo.get_snapshot(self.upload_id, 1)
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.approved_revision, rev_after_accept)
        self.assertEqual(snapshot.reviewer_id, "reviewer")
        self.assertGreaterEqual(len(snapshot.nodes), 1)

    def test_04_approval_occ_conflict_raises_http_409(self):
        """approve_resolved_graph raises HTTPException(409) on revision mismatch."""
        service = AcademicReviewService(self.db)
        rev_after_accept = self._accept_all_nodes(service)
        # Pass wrong revision (0 instead of rev_after_accept)
        with self.assertRaises(HTTPException) as ctx:
            service.approve_resolved_graph(
                upload_id=self.upload_id,
                expected_revision=0,
                user_id="reviewer"
            )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("Revision mismatch", ctx.exception.detail)

    def test_05_approval_api_occ_returns_409(self):
        """POST /approve with stale revision returns HTTP 409."""
        service = AcademicReviewService(self.db)
        self._accept_all_nodes(service)
        # Post with revision=0 (stale — already at rev_after_accept)
        response = self.client.post(
            f"/api/v1/academic/review/{self.upload_id}/approve",
            json={"expected_revision": 0}
        )
        self.assertEqual(response.status_code, 409)

    def test_06_approval_api_readiness_blocked_returns_error(self):
        """POST /approve when preconditions fail (unreviewed nodes) returns an error status."""
        # No accepts done — should fail readiness
        response = self.client.post(
            f"/api/v1/academic/review/{self.upload_id}/approve",
            json={"expected_revision": 0}
        )
        self.assertIn(response.status_code, [400, 409, 422])

    # ─────────────────────────────────────────────────────────────────────────
    # SNAPSHOT IMMUTABILITY TESTS
    # ─────────────────────────────────────────────────────────────────────────

    def test_07_approval_version_unique_constraint(self):
        """Duplicate approval_version for same upload_id triggers IntegrityError."""
        snap1 = AcademicGraphSnapshot(
            upload_id=self.upload_id,
            pipeline_run_id="run_1",
            approval_version=1,
            approved_revision=0,
            base_graph_fingerprint="bfp1",
            resolved_graph_fingerprint="rfp1",
            approval_timestamp=time.time(),
            reviewer_id="reviewer",
            nodes=[], edges=[]
        )
        self.db.add(snap1)
        self.db.commit()

        snap2 = AcademicGraphSnapshot(
            upload_id=self.upload_id,
            pipeline_run_id="run_2",
            approval_version=1,
            approved_revision=1,
            base_graph_fingerprint="bfp2",
            resolved_graph_fingerprint="rfp2",
            approval_timestamp=time.time(),
            reviewer_id="reviewer",
            nodes=[], edges=[]
        )
        self.db.add(snap2)
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    def test_08_monotonic_approval_versions(self):
        """Sequential approvals produce strictly ascending version numbers."""
        service = AcademicReviewService(self.db)

        # First approval cycle: accept all -> approve v1
        rev1 = self._accept_all_nodes(service)
        r1 = service.approve_resolved_graph(
            upload_id=self.upload_id, expected_revision=rev1, user_id="reviewer"
        )
        self.assertEqual(r1["approval_version"], "v1")

        # Second approval cycle: revision advanced to rev1+1 after approve
        # Accept all nodes again (re-accept, revision advances further)
        rev2 = self._accept_all_nodes(service)
        r2 = service.approve_resolved_graph(
            upload_id=self.upload_id, expected_revision=rev2, user_id="reviewer"
        )
        self.assertEqual(r2["approval_version"], "v2")

        snapshots = service.review_repo.list_snapshots(self.upload_id)
        self.assertEqual(len(snapshots), 2)
        versions = [s.approval_version for s in snapshots]
        self.assertEqual(sorted(versions), versions)

    # ─────────────────────────────────────────────────────────────────────────
    # RERUN INVALIDATION TESTS
    # ─────────────────────────────────────────────────────────────────────────

    def test_09_rerun_invalidation_transitions_to_needs_review(self):
        """Rerun with semantic graph change transitions APPROVED -> NEEDS_REVIEW, preserving snapshot."""
        service = AcademicReviewService(self.db)
        rev = self._accept_all_nodes(service)
        service.approve_resolved_graph(
            upload_id=self.upload_id, expected_revision=rev, user_id="reviewer"
        )

        # Introduce a semantically new HEADING block (fingerprint change)
        new_block = DocumentBlock(
            id=str(_uuid.uuid4()),
            document_id=self.doc.id,
            page_id=self.page.id,
            page_number=1, reading_order=3,
            block_type="HEADING", text="Entanglement Theory: A New Chapter",
            heading_level=1,
            x0=10.0, y0=100.0, x1=200.0, y1=120.0,
            font_size=18.0, font_family="Arial",
            bold=True, italic=False, confidence=0.95,
            provenance="pdfplumber"
        )
        self.db.add(new_block)
        self.doc.extraction_timestamp = "2026-08-20T13:00:00Z"
        self.db.commit()

        # Clear cache so rerun picks up new content
        from app.services.intelligence.review import service as review_svc
        review_svc._BASE_GRAPH_CACHE.clear()

        service.validate_approval_after_rerun(self.upload_id)

        self.db.expire_all()
        doc = self.db.query(Document).filter(Document.upload_id == self.upload_id).first()
        self.assertEqual(doc.review_state, "NEEDS_REVIEW")

        # v1 snapshot must be preserved
        v1 = service.review_repo.get_snapshot(self.upload_id, 1)
        self.assertIsNotNone(v1)
        self.assertEqual(v1.approval_version, 1)

    def test_10_rerun_no_semantic_change_preserves_approved(self):
        """Rerun with identical resolved graph does NOT flip APPROVED state."""
        service = AcademicReviewService(self.db)
        rev = self._accept_all_nodes(service)
        service.approve_resolved_graph(
            upload_id=self.upload_id, expected_revision=rev, user_id="reviewer"
        )
        # Validate without any semantic content change
        service.validate_approval_after_rerun(self.upload_id)
        self.db.expire_all()
        doc = self.db.query(Document).filter(Document.upload_id == self.upload_id).first()
        self.assertEqual(doc.review_state, "APPROVED")

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 6 BOUNDARY TESTS
    # ─────────────────────────────────────────────────────────────────────────

    def test_11_phase6_boundary_404_when_not_approved(self):
        """GET /graph/{upload_id} returns 404 when document not yet approved."""
        response = self.client.get(f"/api/v1/academic/graph/{self.upload_id}")
        self.assertEqual(response.status_code, 404)

    def test_12_phase6_boundary_returns_approved_snapshot(self):
        """GET /graph/{upload_id} returns approved snapshot data."""
        service = AcademicReviewService(self.db)
        rev = self._accept_all_nodes(service)
        service.approve_resolved_graph(
            upload_id=self.upload_id, expected_revision=rev, user_id="reviewer"
        )
        response = self.client.get(f"/api/v1/academic/graph/{self.upload_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["upload_id"], self.upload_id)
        self.assertEqual(data["approval_version"], "v1")
        self.assertIn("nodes", data)
        self.assertIn("resolved_graph_fingerprint", data)
        self.assertGreaterEqual(len(data["nodes"]), 1)

    # ─────────────────────────────────────────────────────────────────────────
    # API STRUCTURE TESTS
    # ─────────────────────────────────────────────────────────────────────────

    def test_13_readiness_api_returns_structured_checks(self):
        """GET /approval-readiness returns structured check objects with code/passed/severity."""
        response = self.client.get(
            f"/api/v1/academic/review/{self.upload_id}/approval-readiness"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertIn("eligible", data)
        self.assertIn("checks", data)
        self.assertIn("blocking_reasons", data)
        self.assertIsInstance(data["checks"], list)
        for check in data["checks"]:
            self.assertIn("code", check)
            self.assertIn("passed", check)
            self.assertIn("severity", check)

    # ─────────────────────────────────────────────────────────────────────────
    # REVISION MONOTONICITY
    # ─────────────────────────────────────────────────────────────────────────

    def test_14_revision_monotonically_increases(self):
        """Review revision strictly increases with each successful mutation."""
        service = AcademicReviewService(self.db)
        base_nodes, _ = service.get_base_graph(self.upload_id)
        anchor_key = base_nodes[0].anchor_key
        revisions = []
        for _ in range(3):
            current = service.review_repo.get_or_create_revision(self.upload_id)
            revisions.append(current)
            service.apply_review_action(
                upload_id=self.upload_id,
                action_type="ACCEPT_NODE",
                payload={"target_anchor_key": anchor_key},
                expected_version=current,
                user_id="reviewer"
            )
        for i in range(1, len(revisions)):
            self.assertGreater(revisions[i], revisions[i - 1])


if __name__ == "__main__":
    unittest.main()
