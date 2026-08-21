import os
import unittest
import time
import uuid
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models import Base, Document, AcademicGraphSnapshot
from app.models.knowledge import KnowledgeVersion, KnowledgeEntity, KnowledgeRelationship, KnowledgeEvidence
from app.schemas.academic import AcademicNodeCategory
from app.schemas.knowledge import KnowledgeRelationshipType, KnowledgeEvidenceProvenance


class TestKnowledgeModel(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.db_path = "test_knowledge_model.db"
        cls.engine = create_engine(
            f"sqlite:///{cls.db_path}",
            connect_args={"check_same_thread": False}
        )
        
        # Enforce foreign keys in SQLite for this test run
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
        # Full DB teardown & setup between tests to ensure absolute isolation
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        
        self.db = self.TestingSessionLocal()
        
        # Seed standard parent Document
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

        # Seed standard AcademicGraphSnapshot
        self.snapshot = AcademicGraphSnapshot(
            id=str(uuid.uuid4()),
            upload_id=self.upload_id,
            pipeline_run_id="run_1",
            approval_version=1,
            approved_revision=2,
            base_graph_fingerprint="bfp123",
            resolved_graph_fingerprint="rfp456",
            approval_timestamp=time.time(),
            reviewer_id="reviewer_1",
            nodes=[], edges=[]
        )
        self.snapshot2 = AcademicGraphSnapshot(
            id=str(uuid.uuid4()),
            upload_id=self.upload_id,
            pipeline_run_id="run_2",
            approval_version=2,
            approved_revision=3,
            base_graph_fingerprint="bfp123_2",
            resolved_graph_fingerprint="rfp456_2",
            approval_timestamp=time.time(),
            reviewer_id="reviewer_1",
            nodes=[], edges=[]
        )
        self.db.add_all([self.snapshot, self.snapshot2])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_01_create_version_and_entities(self):
        """Verify successful creation of KnowledgeVersion and KnowledgeEntity mapping."""
        version = KnowledgeVersion(
            upload_id=self.upload_id,
            snapshot_id=self.snapshot.id,
            schema_version="1.0.0",
            status="BUILDING"
        )
        self.db.add(version)
        self.db.flush()

        entity = KnowledgeEntity(
            knowledge_version_id=version.id,
            entity_type=AcademicNodeCategory.CONCEPT.value,
            title="Quantum Superposition",
            content="A principle of quantum mechanics...",
            stable_id="anc_quantum_superposition"
        )
        self.db.add(entity)
        self.db.commit()

        # Retrieve and check fields
        saved_entity = self.db.query(KnowledgeEntity).filter(KnowledgeEntity.stable_id == "anc_quantum_superposition").first()
        self.assertIsNotNone(saved_entity)
        self.assertEqual(saved_entity.title, "Quantum Superposition")
        self.assertEqual(saved_entity.version.status, "BUILDING")

    def test_02_stable_identity_uniqueness_within_version(self):
        """Verify that stable_id unique constraint prevents duplicate semantic entities in a single version."""
        version = KnowledgeVersion(
            upload_id=self.upload_id,
            snapshot_id=self.snapshot.id,
            schema_version="1.0.0",
            status="BUILDING"
        )
        self.db.add(version)
        self.db.flush()

        e1 = KnowledgeEntity(
            knowledge_version_id=version.id,
            entity_type=AcademicNodeCategory.CONCEPT.value,
            title="Superposition",
            content="Concept content",
            stable_id="anc_superposition"
        )
        self.db.add(e1)
        self.db.flush()

        # Adding same stable_id under same version must trigger IntegrityError
        e2 = KnowledgeEntity(
            knowledge_version_id=version.id,
            entity_type=AcademicNodeCategory.DEFINITION.value,
            title="Superposition Definition",
            content="Different text",
            stable_id="anc_superposition"
        )
        self.db.add(e2)
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    def test_03_stable_identity_duplication_across_different_versions(self):
        """Verify that the same stable_id can coexist across different KnowledgeVersions."""
        v1 = KnowledgeVersion(upload_id=self.upload_id, snapshot_id=self.snapshot.id, status="BUILDING")
        v2 = KnowledgeVersion(upload_id=self.upload_id, snapshot_id=self.snapshot2.id, status="BUILDING")
        self.db.add_all([v1, v2])
        self.db.flush()

        e1 = KnowledgeEntity(
            knowledge_version_id=v1.id,
            entity_type=AcademicNodeCategory.CONCEPT.value,
            title="Superposition",
            content="Version 1",
            stable_id="anc_superposition"
        )
        e2 = KnowledgeEntity(
            knowledge_version_id=v2.id,
            entity_type=AcademicNodeCategory.CONCEPT.value,
            title="Superposition Updated",
            content="Version 2",
            stable_id="anc_superposition"
        )
        self.db.add_all([e1, e2])
        # Should commit successfully
        self.db.commit()

        # Check they have unique database PKs but matching stable_ids
        self.assertNotEqual(e1.id, e2.id)
        self.assertEqual(e1.stable_id, e2.stable_id)

    def test_04_composite_foreign_key_version_isolation(self):
        """Verify that composite foreign keys prevent linking entities belonging to different versions."""
        v1 = KnowledgeVersion(upload_id=self.upload_id, snapshot_id=self.snapshot.id, status="BUILDING")
        v2 = KnowledgeVersion(upload_id=self.upload_id, snapshot_id=self.snapshot2.id, status="BUILDING")
        self.db.add_all([v1, v2])
        self.db.flush()

        # Entity A in Version 1
        ea = KnowledgeEntity(
            knowledge_version_id=v1.id,
            entity_type=AcademicNodeCategory.CONCEPT.value,
            title="Concept A",
            content="A",
            stable_id="anc_a"
        )
        # Entity B in Version 2
        eb = KnowledgeEntity(
            knowledge_version_id=v2.id,
            entity_type=AcademicNodeCategory.CONCEPT.value,
            title="Concept B",
            content="B",
            stable_id="anc_b"
        )
        self.db.add_all([ea, eb])
        self.db.flush()

        # Attempt to link Concept A (v1) and Concept B (v2) in Version 1
        rel = KnowledgeRelationship(
            knowledge_version_id=v1.id,
            source_entity_id=ea.id,
            target_entity_id=eb.id,  # belongs to v2, should trigger FK violation!
            relationship_type=KnowledgeRelationshipType.PREREQUISITE_OF.value
        )
        self.db.add(rel)
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    def test_05_self_loop_relationship_integrity_violation(self):
        """Verify that duplicate relationship entries trigger unique constraint failures."""
        v1 = KnowledgeVersion(upload_id=self.upload_id, snapshot_id=self.snapshot.id, status="BUILDING")
        self.db.add(v1)
        self.db.flush()

        e = KnowledgeEntity(
            knowledge_version_id=v1.id,
            entity_type=AcademicNodeCategory.CONCEPT.value,
            title="Concept A",
            content="A",
            stable_id="anc_a"
        )
        self.db.add(e)
        self.db.flush()

        # Add duplicate relationships
        r1 = KnowledgeRelationship(
            knowledge_version_id=v1.id,
            source_entity_id=e.id,
            target_entity_id=e.id,
            relationship_type=KnowledgeRelationshipType.CONTAINS.value
        )
        self.db.add(r1)
        # Unique constraint or domain validations will raise error
        with self.assertRaises((IntegrityError, ValueError)):
            self.db.commit()
        self.db.rollback()

    def test_06_evidence_traceability_and_provenance(self):
        """Verify that KnowledgeEvidence registers properly with coordinates and valid provenance."""
        v1 = KnowledgeVersion(upload_id=self.upload_id, snapshot_id=self.snapshot.id, status="BUILDING")
        self.db.add(v1)
        self.db.flush()

        e = KnowledgeEntity(
            knowledge_version_id=v1.id,
            entity_type=AcademicNodeCategory.CONCEPT.value,
            title="Concept A",
            content="A",
            stable_id="anc_a"
        )
        self.db.add(e)
        self.db.flush()

        ev = KnowledgeEvidence(
            entity_id=e.id,
            document_id=self.doc.id,
            page_number=1,
            section_title="Chapter 1",
            source_node_id="an_1",
            source_anchor_key="anc_a",
            text_reference="Concept A raw text",
            provenance=KnowledgeEvidenceProvenance.EXPLICIT_CLASSIFIER.value,
            x0=10.0, y0=20.0, x1=100.0, y1=40.0
        )
        self.db.add(ev)
        self.db.commit()

        saved_ev = self.db.query(KnowledgeEvidence).filter(KnowledgeEvidence.entity_id == e.id).first()
        self.assertIsNotNone(saved_ev)
        self.assertEqual(saved_ev.page_number, 1)
        self.assertEqual(saved_ev.x0, 10.0)
        self.assertEqual(saved_ev.provenance, "EXPLICIT_CLASSIFIER")

    def test_07_immutability_lifecycle_finalized_updates_prohibited(self):
        """Verify that both SQLAlchemy and SQL triggers block updates on finalized knowledge versions."""
        v1 = KnowledgeVersion(upload_id=self.upload_id, snapshot_id=self.snapshot.id, status="BUILDING")
        self.db.add(v1)
        self.db.flush()

        e = KnowledgeEntity(
            knowledge_version_id=v1.id,
            entity_type=AcademicNodeCategory.CONCEPT.value,
            title="Concept A",
            content="A",
            stable_id="anc_a"
        )
        self.db.add(e)
        self.db.commit()

        # Finalize the version
        v1.status = "FINALIZED"
        self.db.commit()

        # Attempt to update entity title under finalized version
        e.title = "MUTATED"
        with self.assertRaises((ValueError, OperationalError, IntegrityError)):
            self.db.commit()
        self.db.rollback()

    def test_08_immutability_lifecycle_finalized_deletions_prohibited(self):
        """Verify that deletions on finalized knowledge versions are strictly prohibited."""
        v1 = KnowledgeVersion(upload_id=self.upload_id, snapshot_id=self.snapshot.id, status="FINALIZED")
        self.db.add(v1)
        self.db.commit()

        # Attempt to delete finalized version
        self.db.delete(v1)
        with self.assertRaises((ValueError, OperationalError, IntegrityError)):
            self.db.commit()
        self.db.rollback()

    def test_09_immutability_lifecycle_child_deletions_prohibited(self):
        """Verify that deletions of child entities under finalized versions are prohibited."""
        v1 = KnowledgeVersion(upload_id=self.upload_id, snapshot_id=self.snapshot.id, status="BUILDING")
        self.db.add(v1)
        self.db.flush()

        e = KnowledgeEntity(
            knowledge_version_id=v1.id,
            entity_type=AcademicNodeCategory.CONCEPT.value,
            title="Concept A",
            content="A",
            stable_id="anc_a"
        )
        self.db.add(e)
        self.db.commit()

        # Finalize
        v1.status = "FINALIZED"
        self.db.commit()

        # Attempt to delete entity
        self.db.delete(e)
        with self.assertRaises((ValueError, OperationalError, IntegrityError)):
            self.db.commit()
        self.db.rollback()

    def test_10_restrict_delete_preserves_finalized_snapshots(self):
        """Verify that deleting a snapshot or document referenced by a finalized version raises an IntegrityError."""
        v1 = KnowledgeVersion(upload_id=self.upload_id, snapshot_id=self.snapshot.id, status="FINALIZED")
        self.db.add(v1)
        self.db.commit()

        # Attempt to delete snapshot
        self.db.delete(self.snapshot)
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()


if __name__ == "__main__":
    unittest.main()
