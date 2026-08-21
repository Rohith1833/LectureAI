import os
import unittest
import time
import uuid
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from app.models import Base, Document, AcademicGraphSnapshot, DocumentBlock, DocumentPage
from app.models.knowledge import KnowledgeVersion, KnowledgeEntity, KnowledgeRelationship, KnowledgeEvidence
from app.services.intelligence.knowledge_builder import KnowledgeBuilder
from app.schemas.knowledge import KnowledgeRelationshipType, KnowledgeEvidenceProvenance

class TestKnowledgeBuilder(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.db_path = "test_knowledge_builder.db"
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

        # Seed Document Page
        self.page = DocumentPage(
            document_id=self.doc.id,
            page_number=1,
            width=612.0,
            height=792.0
        )
        self.db.add(self.page)
        self.db.flush()

        # Seed Document Block
        self.block_id = "blk_1"
        self.block = DocumentBlock(
            id=self.block_id,
            document_id=self.doc.id,
            page_id=self.page.id,
            page_number=1,
            reading_order=1,
            block_type="PARAGRAPH",
            text="Authoritative source text for Quantum Entanglement.",
            x0=10.0, y0=20.0, x1=110.0, y1=120.0,
            provenance="PEDAGOGICAL_CLASSIFICATION_MODULE"
        )
        self.db.add(self.block)
        self.db.flush()

        # 2. Setup standard AcademicGraphSnapshot
        self.nodes_data = [
            {
                "node_id": "an_concept_1",
                "category": "CONCEPT",
                "title": "Quantum Entanglement",
                "target_block_id": self.block_id,
                "anchor_key": "anc_quantum_entanglement",
                "review_state": "ACCEPTED",
                "metadata": {"provenance": "PEDAGOGICAL_CLASSIFICATION_MODULE"}
            },
            {
                "node_id": "an_def_1",
                "category": "DEFINITION",
                "title": "Quantum Entanglement Definition",
                "target_block_id": self.block_id,
                "anchor_key": "anc_quantum_entanglement_def",
                "review_state": "ACCEPTED",
                "metadata": {"provenance": "PEDAGOGICAL_CLASSIFICATION_MODULE"}
            }
        ]
        self.edges_data = [
            {
                "source_node_id": "an_concept_1",
                "target_node_id": "an_def_1",
                "edge_type": "CONTAINS",
                "confidence": 0.95,
                "metadata": {"is_inferred": False}
            }
        ]

        self.snapshot = AcademicGraphSnapshot(
            upload_id=self.upload_id,
            pipeline_run_id="run_1",
            approval_version=1,
            approved_revision=2,
            base_graph_fingerprint="bfp123",
            resolved_graph_fingerprint="rfp456",
            approval_timestamp=time.time(),
            reviewer_id="reviewer_1",
            nodes=self.nodes_data,
            edges=self.edges_data
        )
        self.db.add(self.snapshot)
        self.db.commit()

        self.builder = KnowledgeBuilder(self.db)

    def tearDown(self):
        self.db.close()

    def test_01_successful_compilation(self):
        """Verify successful compiler execution mapping nodes, relationships, and evidence."""
        version = self.builder.compile_snapshot(self.snapshot.id)
        self.assertIsNotNone(version)
        self.assertEqual(version.status, "FINALIZED")
        self.assertEqual(version.snapshot_id, self.snapshot.id)

        # Verify entities
        entities = self.db.query(KnowledgeEntity).filter(KnowledgeEntity.knowledge_version_id == version.id).all()
        self.assertEqual(len(entities), 2)
        entity_titles = {e.title for e in entities}
        self.assertIn("Quantum Entanglement", entity_titles)
        self.assertIn("Quantum Entanglement Definition", entity_titles)

        # Verify evidence
        ev1 = self.db.query(KnowledgeEvidence).filter(KnowledgeEvidence.source_anchor_key == "anc_quantum_entanglement").first()
        self.assertIsNotNone(ev1)
        self.assertEqual(ev1.page_number, 1)
        self.assertEqual(ev1.x0, 10.0)
        self.assertEqual(ev1.provenance, KnowledgeEvidenceProvenance.EXPLICIT_CLASSIFIER.value)

        # Verify relationships
        rels = self.db.query(KnowledgeRelationship).filter(KnowledgeRelationship.knowledge_version_id == version.id).all()
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0].relationship_type, KnowledgeRelationshipType.CONTAINS.value)
        self.assertEqual(rels[0].confidence, 0.95)

    def test_02_snapshot_unapproved_rejected(self):
        """Verify compilation fails if the target document is not APPROVED."""
        self.doc.review_state = "NEEDS_REVIEW"
        self.db.commit()

        with self.assertRaises(ValueError) as ctx:
            self.builder.compile_snapshot(self.snapshot.id)
        self.assertIn("is not APPROVED", str(ctx.exception))

    def test_03_category_contract_filtering(self):
        """Verify that unsupported categories (e.g. UNIT, LEARNING_OBJECTIVE) are explicitly filtered out."""
        # Add unsupported node type to snapshot nodes list
        unsupported_nodes = self.nodes_data + [
            {
                "node_id": "an_unit_1",
                "category": "UNIT",
                "title": "Meta Invariant Unit",
                "target_block_id": self.block_id,
                "anchor_key": "anc_unit_1",
                "review_state": "ACCEPTED",
                "metadata": {}
            },
            {
                "node_id": "an_lo_1",
                "category": "LEARNING_OBJECTIVE",
                "title": "Learning Objective 1",
                "target_block_id": self.block_id,
                "anchor_key": "anc_lo_1",
                "review_state": "ACCEPTED",
                "metadata": {}
            }
        ]
        # Relationship involving unsupported node is also expected to be skipped
        unsupported_edges = self.edges_data + [
            {
                "source_node_id": "an_unit_1",
                "target_node_id": "an_concept_1",
                "edge_type": "CONTAINS",
                "confidence": 0.80
            }
        ]

        new_snapshot = AcademicGraphSnapshot(
            upload_id=self.upload_id,
            pipeline_run_id="run_1",
            approval_version=2,
            approved_revision=3,
            base_graph_fingerprint="bfp1234",
            resolved_graph_fingerprint="rfp4567",
            approval_timestamp=time.time(),
            reviewer_id="reviewer_1",
            nodes=unsupported_nodes,
            edges=unsupported_edges
        )
        self.db.add(new_snapshot)
        self.db.commit()

        version = self.builder.compile_snapshot(new_snapshot.id)
        entities = self.db.query(KnowledgeEntity).filter(KnowledgeEntity.knowledge_version_id == version.id).all()
        # Should only compile the 2 valid categories
        self.assertEqual(len(entities), 2)
        entity_categories = {e.entity_type for e in entities}
        self.assertNotIn("UNIT", entity_categories)
        self.assertNotIn("LEARNING_OBJECTIVE", entity_categories)

        # Verification of edges: should skip relations involving the UNIT node
        rels = self.db.query(KnowledgeRelationship).filter(KnowledgeRelationship.knowledge_version_id == version.id).all()
        self.assertEqual(len(rels), 1)

    def test_04_stable_identity_fallback_ordinary_node_rejection(self):
        """Verify that ordinary nodes missing an anchor_key are rejected."""
        bad_nodes = [
            {
                "node_id": "an_bad_1",
                "category": "CONCEPT",
                "title": "No Anchor key node",
                "target_block_id": self.block_id,
                "anchor_key": None,  # Missing anchor key
                "review_state": "ACCEPTED",
                "metadata": {}
            }
        ]

        new_snapshot = AcademicGraphSnapshot(
            upload_id=self.upload_id,
            pipeline_run_id="run_1",
            approval_version=3,
            approved_revision=4,
            base_graph_fingerprint="bfp_b",
            resolved_graph_fingerprint="rfp_b",
            approval_timestamp=time.time(),
            reviewer_id="reviewer_1",
            nodes=bad_nodes,
            edges=[]
        )
        self.db.add(new_snapshot)
        self.db.commit()

        version = self.builder.compile_snapshot(new_snapshot.id)
        entities = self.db.query(KnowledgeEntity).filter(KnowledgeEntity.knowledge_version_id == version.id).all()
        # Ordinary node rejected because it doesn't have anchor_key
        self.assertEqual(len(entities), 0)

    def test_05_stable_identity_manual_override_preserved(self):
        """Verify manual override nodes preserve their manual anchor_keys."""
        manual_nodes = [
            {
                "node_id": "an_manual_1",
                "category": "CONCEPT",
                "title": "Human Concept",
                "target_block_id": None,
                "anchor_key": "anc_manual_override_123",
                "review_state": "MODIFIED",
                "metadata": {"provenance": "HUMAN_OVERRIDE"}
            }
        ]

        new_snapshot = AcademicGraphSnapshot(
            upload_id=self.upload_id,
            pipeline_run_id="run_1",
            approval_version=4,
            approved_revision=5,
            base_graph_fingerprint="bfp_m",
            resolved_graph_fingerprint="rfp_m",
            approval_timestamp=time.time(),
            reviewer_id="reviewer_1",
            nodes=manual_nodes,
            edges=[]
        )
        self.db.add(new_snapshot)
        self.db.commit()

        version = self.builder.compile_snapshot(new_snapshot.id)
        entity = self.db.query(KnowledgeEntity).filter(KnowledgeEntity.knowledge_version_id == version.id).first()
        self.assertIsNotNone(entity)
        self.assertEqual(entity.stable_id, "anc_manual_override_123")

    def test_06_evidence_missing_stale_fallback(self):
        """Verify missing or stale target_block_id resolves to fallback evidence coordinates/provenance."""
        stale_nodes = [
            {
                "node_id": "an_stale_1",
                "category": "CONCEPT",
                "title": "Quantum Entanglement",
                "target_block_id": "nonexistent_block_id",  # Invalid block reference
                "anchor_key": "anc_stale_concept",
                "review_state": "ACCEPTED",
                "metadata": {"provenance": "PEDAGOGICAL_CLASSIFICATION_MODULE"}
            }
        ]

        new_snapshot = AcademicGraphSnapshot(
            upload_id=self.upload_id,
            pipeline_run_id="run_1",
            approval_version=5,
            approved_revision=6,
            base_graph_fingerprint="bfp_s",
            resolved_graph_fingerprint="rfp_s",
            approval_timestamp=time.time(),
            reviewer_id="reviewer_1",
            nodes=stale_nodes,
            edges=[]
        )
        self.db.add(new_snapshot)
        self.db.commit()

        version = self.builder.compile_snapshot(new_snapshot.id)
        evidence = self.db.query(KnowledgeEvidence).filter(KnowledgeEvidence.source_anchor_key == "anc_stale_concept").first()
        self.assertIsNotNone(evidence)
        # Should fallback to Page None, null coordinates, and UNKNOWN provenance
        self.assertIsNone(evidence.page_number)
        self.assertIsNone(evidence.x0)
        self.assertEqual(evidence.provenance, KnowledgeEvidenceProvenance.UNKNOWN.value)

    def test_07_idempotency_finalized_return(self):
        """Verify re-running compilation for a snapshot returns the existing finalized version."""
        v1 = self.builder.compile_snapshot(self.snapshot.id)
        self.assertIsNotNone(v1)

        v2 = self.builder.compile_snapshot(self.snapshot.id)
        self.assertEqual(v1.id, v2.id)

    def test_08_concurrency_unique_constraint(self):
        """Verify uq_kv_snapshot_id unique constraint blocks duplicate compiled versions."""
        # Manually seed a finalized version
        v = KnowledgeVersion(
            id=str(uuid.uuid4()),
            upload_id=self.upload_id,
            snapshot_id=self.snapshot.id,
            status="FINALIZED"
        )
        self.db.add(v)
        self.db.commit()

        # Attempting to manually add another KnowledgeVersion with same snapshot_id will raise IntegrityError
        v_duplicate = KnowledgeVersion(
            id=str(uuid.uuid4()),
            upload_id=self.upload_id,
            snapshot_id=self.snapshot.id,
            status="FINALIZED"
        )
        self.db.add(v_duplicate)
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

if __name__ == "__main__":
    unittest.main()
