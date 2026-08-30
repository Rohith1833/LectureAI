import unittest
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db
from app.models import Base, Document, DocumentBlock, DocumentPage, DocumentMetadata
from app.models.knowledge import KnowledgeVersion, KnowledgeEntity
from app.services.intelligence.review.service import AcademicReviewService
from app.schemas.review import NodeReviewState


class TestReviewBulkAcceptAndKnowledgeFinalization(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.TestingSessionLocal = sessionmaker(bind=self.engine)
        self.db = self.TestingSessionLocal()

        self.upload_id = "upload_test_bulk"
        self.doc_id = str(uuid.uuid4())

        self.doc = Document(
            id=self.doc_id,
            upload_id=self.upload_id,
            status="processed",
            review_state="NEEDS_REVIEW",
            processing_time=1.0,
            extraction_timestamp="2026-08-29T12:00:00",
        )
        self.db.add(self.doc)

        self.meta = DocumentMetadata(
            id=str(uuid.uuid4()),
            document_id=self.doc_id,
            title="Lecture Notes",
            page_count=2,
        )
        self.db.add(self.meta)

        self.page1 = DocumentPage(
            id=str(uuid.uuid4()),
            document_id=self.doc_id,
            page_number=1,
            width=612.0,
            height=792.0,
        )
        self.db.add(self.page1)

        self.block1 = DocumentBlock(
            id="blk_001",
            document_id=self.doc_id,
            page_id=self.page1.id,
            page_number=1,
            reading_order=1,
            block_type="HEADING",
            text="Chapter 1: Neural Networks",
            x0=50.0,
            y0=50.0,
            x1=500.0,
            y1=70.0,
            heading_level=1,
            confidence=0.95,
        )
        self.block2 = DocumentBlock(
            id="blk_002",
            document_id=self.doc_id,
            page_id=self.page1.id,
            page_number=1,
            reading_order=2,
            block_type="PARAGRAPH",
            text="Definition: Backpropagation is an algorithm...",
            x0=50.0,
            y0=80.0,
            x1=500.0,
            y1=120.0,
            confidence=0.90,
        )
        self.db.add(self.block1)
        self.db.add(self.block2)
        self.db.commit()

        from app.services.intelligence.review import service as review_svc
        review_svc._BASE_GRAPH_CACHE.clear()

        self.service = AcademicReviewService(self.db)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_bulk_accept_and_auto_compile_knowledge(self):
        # 1. Base graph has unreviewed nodes
        summary = self.service.get_review_summary(self.upload_id)
        self.assertGreater(summary["unreviewed_count"], 0)
        self.assertEqual(summary["accepted_count"], 0)

        # 2. Readiness check fails initially because nodes are unreviewed
        readiness = self.service.check_approval_readiness(self.upload_id)
        self.assertFalse(readiness["eligible"])
        self.assertTrue(any("unreviewed" in b.lower() for b in readiness["blocking_reasons"]))

        # 3. Apply ACCEPT_ALL_NODES action
        rev = self.service.review_repo.get_or_create_revision(self.upload_id)
        res = self.service.apply_review_action(
            upload_id=self.upload_id,
            action_type="ACCEPT_ALL_NODES",
            payload={},
            expected_version=rev,
            user_id="reviewer_1",
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["override_id"], "bulk")

        # 4. Summary reflects all nodes accepted
        new_summary = self.service.get_review_summary(self.upload_id)
        self.assertEqual(new_summary["unreviewed_count"], 0)
        self.assertGreater(new_summary["accepted_count"], 0)

        # 5. Readiness check passes
        new_readiness = self.service.check_approval_readiness(self.upload_id)
        self.assertTrue(new_readiness["eligible"])
        self.assertEqual(len(new_readiness["blocking_reasons"]), 0)

        # 6. Approve graph snapshot
        approval_res = self.service.approve_resolved_graph(
            upload_id=self.upload_id,
            expected_revision=res["new_version"],
            user_id="reviewer_1",
        )
        self.assertTrue(approval_res["success"])
        self.assertEqual(approval_res["approval_version"], "v1")

        # 7. Document review state is APPROVED
        self.assertEqual(self.doc.review_state, "APPROVED")

        # 8. KnowledgeVersion was compiled automatically and is in FINALIZED state
        kv = (
            self.db.query(KnowledgeVersion)
            .filter(KnowledgeVersion.upload_id == self.upload_id)
            .first()
        )
        self.assertIsNotNone(kv)
        self.assertEqual(kv.status, "FINALIZED")

        # 9. Entities were compiled
        entities = (
            self.db.query(KnowledgeEntity)
            .filter(KnowledgeEntity.knowledge_version_id == kv.id)
            .all()
        )
        self.assertGreater(len(entities), 0)

    def test_bulk_accept_scalability_large_graph_250_nodes(self):
        """Regression test: verify Accept All handles >= 250 academic nodes efficiently and reliably."""
        large_upload_id = "upload_large_scale_250"
        large_doc_id = str(uuid.uuid4())

        large_doc = Document(
            id=large_doc_id,
            upload_id=large_upload_id,
            status="processed",
            review_state="NEEDS_REVIEW",
            processing_time=2.0,
            extraction_timestamp="2026-08-29T12:00:00",
        )
        self.db.add(large_doc)

        meta = DocumentMetadata(
            id=str(uuid.uuid4()),
            document_id=large_doc_id,
            title="Massive Textbook",
            page_count=50,
        )
        self.db.add(meta)

        page = DocumentPage(
            id=str(uuid.uuid4()),
            document_id=large_doc_id,
            page_number=1,
            width=612.0,
            height=792.0,
        )
        self.db.add(page)

        # Create 260 blocks to generate >= 250 distinct nodes in the academic graph
        for i in range(1, 261):
            category_prefix = "Definition" if i % 2 == 0 else "Theorem"
            block = DocumentBlock(
                id=f"blk_large_{i:04d}",
                document_id=large_doc_id,
                page_id=page.id,
                page_number=1,
                reading_order=i,
                block_type="PARAGRAPH" if i % 10 != 1 else "HEADING",
                text=f"{category_prefix} {i}: Mathematical statement and derivation details for concept {i}.",
                x0=50.0,
                y0=50.0 + (i * 2.0),
                x1=500.0,
                y1=60.0 + (i * 2.0),
                heading_level=2 if i % 10 == 1 else None,
                confidence=0.92,
            )
            self.db.add(block)
        
        self.db.commit()

        # Check that we have >= 250 unreviewed nodes
        summary = self.service.get_review_summary(large_upload_id)
        self.assertGreaterEqual(summary["unreviewed_count"], 250)
        self.assertEqual(summary["accepted_count"], 0)

        # Apply ACCEPT_ALL_NODES
        rev = self.service.review_repo.get_or_create_revision(large_upload_id)
        res = self.service.apply_review_action(
            upload_id=large_upload_id,
            action_type="ACCEPT_ALL_NODES",
            payload={},
            expected_version=rev,
            user_id="reviewer_scaler",
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["override_id"], "bulk")

        # Verify summary reflects all nodes are accepted
        updated_summary = self.service.get_review_summary(large_upload_id)
        self.assertEqual(updated_summary["unreviewed_count"], 0)
        self.assertGreaterEqual(updated_summary["accepted_count"], 250)

        # Check approval readiness
        readiness = self.service.check_approval_readiness(large_upload_id)
        self.assertTrue(readiness["eligible"])
        self.assertEqual(len(readiness["blocking_reasons"]), 0)

        # Approve and verify finalized knowledge version
        approval_res = self.service.approve_resolved_graph(
            upload_id=large_upload_id,
            expected_revision=res["new_version"],
            user_id="reviewer_scaler",
        )
        self.assertTrue(approval_res["success"])
        self.assertEqual(large_doc.review_state, "APPROVED")

        kv = (
            self.db.query(KnowledgeVersion)
            .filter(KnowledgeVersion.upload_id == large_upload_id)
            .first()
        )
        self.assertIsNotNone(kv)
        self.assertEqual(kv.status, "FINALIZED")

        entities = (
            self.db.query(KnowledgeEntity)
            .filter(KnowledgeEntity.knowledge_version_id == kv.id)
            .all()
        )
        self.assertGreaterEqual(len(entities), 250)

    def test_individual_node_review_unchanged(self):
        """Verify that individual node review actions remain fully functional and unchanged."""
        single_upload_id = "upload_single_node_test"
        single_doc_id = str(uuid.uuid4())

        single_doc = Document(
            id=single_doc_id,
            upload_id=single_upload_id,
            status="processed",
            review_state="NEEDS_REVIEW",
            processing_time=1.0,
            extraction_timestamp="2026-08-29T12:00:00",
        )
        self.db.add(single_doc)
        self.db.add(DocumentMetadata(id=str(uuid.uuid4()), document_id=single_doc_id, title="Single Doc", page_count=1))
        page = DocumentPage(id=str(uuid.uuid4()), document_id=single_doc_id, page_number=1, width=612.0, height=792.0)
        self.db.add(page)
        self.db.add(DocumentBlock(
            id="blk_single_1",
            document_id=single_doc_id,
            page_id=page.id,
            page_number=1,
            reading_order=1,
            block_type="PARAGRAPH",
            text="Definition 1: Singular value decomposition.",
            x0=50.0, y0=50.0, x1=500.0, y1=70.0,
            confidence=0.95
        ))
        self.db.commit()

        graph = self.service.get_resolved_graph(single_upload_id)
        node = graph["nodes"][0]

        rev = self.service.review_repo.get_or_create_revision(single_upload_id)
        res = self.service.apply_review_action(
            upload_id=single_upload_id,
            action_type="ACCEPT_NODE",
            payload={"target_anchor_key": node["anchor_key"]},
            expected_version=rev,
            user_id="reviewer_single",
        )
        self.assertTrue(res["success"])
        self.assertNotEqual(res["override_id"], "bulk")

        summary = self.service.get_review_summary(single_upload_id)
        self.assertEqual(summary["accepted_count"], 1)
        self.assertEqual(summary["unreviewed_count"], 0)


if __name__ == "__main__":
    unittest.main()

