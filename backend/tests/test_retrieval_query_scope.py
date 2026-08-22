import os
import unittest
import time
import uuid
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from pydantic import ValidationError

from app.models import Base, Document, AcademicGraphSnapshot
from app.models.knowledge import KnowledgeVersion
from app.repositories.knowledge_repository import KnowledgeRepository
from app.schemas.retrieval import RetrievalScope, RetrievalOptions, RetrievalRequest
from app.services.retrieval.query_normalizer import QueryNormalizer
from app.services.retrieval.scope_resolver import ScopeResolver, ResolvedScope


class TestRetrievalQueryScope(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.db_path = "test_retrieval_query_scope.db"
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
        self.repo = KnowledgeRepository(self.db)
        self.normalizer = QueryNormalizer()
        self.resolver = ScopeResolver(self.repo)

        # Seed initial documents, snapshots and versions for resolver testing
        self.upload_a = str(uuid.uuid4())
        self.doc_a = Document(
            id="doc_a_id",
            upload_id=self.upload_a,
            status="processed",
            extraction_timestamp="2026-08-21T12:00:00Z",
            processing_time=1.0,
            review_state="APPROVED"
        )

        self.upload_b = str(uuid.uuid4())
        self.doc_b = Document(
            id="doc_b_id",
            upload_id=self.upload_b,
            status="processed",
            extraction_timestamp="2026-08-21T12:00:00Z",
            processing_time=1.0,
            review_state="APPROVED"
        )
        self.db.add_all([self.doc_a, self.doc_b])
        self.db.flush()

        # Snapshot and Version metadata mapping for doc A
        self.snap_a1 = AcademicGraphSnapshot(
            id="snap_a1_id",
            upload_id=self.upload_a,
            pipeline_run_id="run_a1",
            approval_version=1,
            approved_revision=2,
            base_graph_fingerprint="bfp_a1",
            resolved_graph_fingerprint="rfp_a1",
            approval_timestamp=time.time() - 200,
            reviewer_id="reviewer",
            nodes=[], edges=[]
        )
        self.snap_a2 = AcademicGraphSnapshot(
            id="snap_a2_id",
            upload_id=self.upload_a,
            pipeline_run_id="run_a2",
            approval_version=2,
            approved_revision=4,
            base_graph_fingerprint="bfp_a2",
            resolved_graph_fingerprint="rfp_a2",
            approval_timestamp=time.time() - 100,
            reviewer_id="reviewer",
            nodes=[], edges=[]
        )
        self.snap_a_building = AcademicGraphSnapshot(
            id="snap_a_building_id",
            upload_id=self.upload_a,
            pipeline_run_id="run_a_build",
            approval_version=3,
            approved_revision=5,
            base_graph_fingerprint="bfp_a_build",
            resolved_graph_fingerprint="rfp_a_build",
            approval_timestamp=time.time(),
            reviewer_id="reviewer",
            nodes=[], edges=[]
        )

        # Snapshot for doc B
        self.snap_b1 = AcademicGraphSnapshot(
            id="snap_b1_id",
            upload_id=self.upload_b,
            pipeline_run_id="run_b1",
            approval_version=1,
            approved_revision=2,
            base_graph_fingerprint="bfp_b1",
            resolved_graph_fingerprint="rfp_b1",
            approval_timestamp=time.time(),
            reviewer_id="reviewer",
            nodes=[], edges=[]
        )
        self.db.add_all([self.snap_a1, self.snap_a2, self.snap_a_building, self.snap_b1])
        self.db.flush()

        # Seed KnowledgeVersions (Building status to bypass finalization validation first)
        self.v_a1 = KnowledgeVersion(
            id="v_a1_id",
            upload_id=self.upload_a,
            snapshot_id="snap_a1_id",
            status="BUILDING",
            created_at=time.time() - 200
        )
        self.v_a2 = KnowledgeVersion(
            id="v_a2_id",
            upload_id=self.upload_a,
            snapshot_id="snap_a2_id",
            status="BUILDING",
            created_at=time.time() - 100
        )
        self.v_a_building = KnowledgeVersion(
            id="v_a_building_id",
            upload_id=self.upload_a,
            snapshot_id="snap_a_building_id",
            status="BUILDING",
            created_at=time.time()
        )
        self.v_b1 = KnowledgeVersion(
            id="v_b1_id",
            upload_id=self.upload_b,
            snapshot_id="snap_b1_id",
            status="BUILDING",
            created_at=time.time()
        )
        self.db.add_all([self.v_a1, self.v_a2, self.v_a_building, self.v_b1])
        self.db.flush()

        # Finalize the target ones
        self.v_a1.status = "FINALIZED"
        self.v_a2.status = "FINALIZED"
        self.v_b1.status = "FINALIZED"
        self.db.commit()

    def tearDown(self):
        self.db.close()

    # ─── QUERY NORMALIZER TESTS ───────────────────────────────────

    def test_01_query_normalizer_normal_query(self):
        """Verify normal query tokenization."""
        res = self.normalizer.normalize("Quantum Entanglement")
        self.assertEqual(res.terms, ["quantum", "entanglement"])

    def test_02_query_normalizer_leading_whitespace(self):
        """Verify query with leading whitespace is trimmed."""
        res = self.normalizer.normalize("   quantum physics")
        self.assertEqual(res.terms, ["quantum", "physics"])

    def test_03_query_normalizer_trailing_whitespace(self):
        """Verify query with trailing whitespace is trimmed."""
        res = self.normalizer.normalize("quantum physics   ")
        self.assertEqual(res.terms, ["quantum", "physics"])

    def test_04_query_normalizer_mixed_case(self):
        """Verify query case is normalized to lowercase."""
        res = self.normalizer.normalize("QuAnTuM pHySiCs")
        self.assertEqual(res.terms, ["quantum", "physics"])

    def test_05_query_normalizer_repeated_terms(self):
        """Verify duplicate terms are removed while maintaining insertion order."""
        res = self.normalizer.normalize("physics quantum physics theory quantum")
        self.assertEqual(res.terms, ["physics", "quantum", "theory"])

    def test_06_query_normalizer_repeated_whitespace(self):
        """Verify repeated internal whitespace is collapsed."""
        res = self.normalizer.normalize("quantum     physics    theory")
        self.assertEqual(res.terms, ["quantum", "physics", "theory"])

    def test_07_query_normalizer_punctuation_handling(self):
        """Verify common punctuation marks are stripped and act as token separators."""
        res = self.normalizer.normalize("quantum-entanglement! (physics: theory?)")
        # re.split('[^a-zA-Z0-9]+') will split quantum-entanglement and strip brackets
        self.assertEqual(res.terms, ["quantum", "entanglement", "physics", "theory"])

    def test_08_query_normalizer_empty_query(self):
        """Verify empty raw query produces empty terms."""
        res = self.normalizer.normalize("")
        self.assertEqual(res.terms, [])

    def test_09_query_normalizer_whitespace_only_query(self):
        """Verify whitespace-only query produces empty terms."""
        res = self.normalizer.normalize("      ")
        self.assertEqual(res.terms, [])

    def test_10_query_normalizer_maximum_allowed_query_length(self):
        """Verify max query length (2048 chars) normalizes successfully."""
        long_query = "quantum " * 256  # 2048 chars
        res = self.normalizer.normalize(long_query)
        self.assertEqual(res.terms, ["quantum"])

    def test_11_query_normalizer_deterministic_repeated_execution(self):
        """Verify normalization is deterministic and reproducible."""
        q = "Quantum Entanglement!"
        res1 = self.normalizer.normalize(q)
        res2 = self.normalizer.normalize(q)
        self.assertEqual(res1, res2)

    def test_12_query_normalizer_preservation_of_raw_query(self):
        """Verify original raw query is preserved unaltered."""
        q = "  Quantum Entanglement!  "
        res = self.normalizer.normalize(q)
        self.assertEqual(res.raw, q)
        self.assertEqual(res.normalized, "quantum entanglement!")

    # ─── SCOPE RESOLVER TESTS ─────────────────────────────────────

    def test_13_scope_resolver_explicit_finalized_version(self):
        """Verify resolution of an explicitly defined finalized version ID."""
        scope = RetrievalScope(document_id="doc_a_id", version_id="v_a1_id")
        resolved = self.resolver.resolve(scope)
        self.assertEqual(resolved.document_id, "doc_a_id")
        self.assertEqual(resolved.version_id, "v_a1_id")

    def test_14_scope_resolver_latest_finalized_version(self):
        """Verify version_id=None resolves to the latest finalized version version descending."""
        scope = RetrievalScope(document_id="doc_a_id", version_id=None)
        resolved = self.resolver.resolve(scope)
        # Should resolve to v_a2_id (approval_version=2 snapshot)
        self.assertEqual(resolved.document_id, "doc_a_id")
        self.assertEqual(resolved.version_id, "v_a2_id")

    def test_15_scope_resolver_explicit_version_remains_selected(self):
        """Verify explicit selection remains pinned even if a newer finalized version exists."""
        # Request older v_a1_id explicitly, even though newer v_a2_id exists
        scope = RetrievalScope(document_id="doc_a_id", version_id="v_a1_id")
        resolved = self.resolver.resolve(scope)
        self.assertEqual(resolved.version_id, "v_a1_id")

    def test_16_scope_resolver_building_version_rejected(self):
        """Verify explicit request for a BUILDING status version raises ValueError."""
        scope = RetrievalScope(document_id="doc_a_id", version_id="v_a_building_id")
        with self.assertRaises(ValueError) as context:
            self.resolver.resolve(scope)
        self.assertIn("is not finalized", str(context.exception))


    def test_17_scope_resolver_no_finalized_version(self):
        """Verify document with no finalized version raises ValueError."""
        # Create a new document C with no versions at all
        upload_c = str(uuid.uuid4())
        doc_c = Document(
            id="doc_c_id",
            upload_id=upload_c,
            status="processed",
            extraction_timestamp="2026-08-21T12:00:00Z",
            processing_time=1.0,
            review_state="APPROVED"
        )
        self.db.add(doc_c)
        self.db.commit()

        scope = RetrievalScope(document_id="doc_c_id", version_id=None)
        with self.assertRaises(ValueError) as context:
            self.resolver.resolve(scope)
        self.assertIn("No finalized KnowledgeVersion found", str(context.exception))

    def test_18_scope_resolver_document_not_found(self):
        """Verify non-existent document ID raises ValueError."""
        scope = RetrievalScope(document_id="doc_non_existent", version_id=None)
        with self.assertRaises(ValueError) as context:
            self.resolver.resolve(scope)
        self.assertIn("Document with ID 'doc_non_existent' not found", str(context.exception))

    def test_19_scope_resolver_version_not_found(self):
        """Verify non-existent version ID explicitly requested raises ValueError."""
        scope = RetrievalScope(document_id="doc_a_id", version_id="v_non_existent")
        with self.assertRaises(ValueError) as context:
            self.resolver.resolve(scope)
        self.assertIn("not found", str(context.exception))

    def test_20_scope_resolver_version_belonging_to_another_document_rejected(self):
        """Verify version belonging to document B requested under document A scope is rejected."""
        # v_b1_id belongs to doc_b_id, request it under doc_a_id scope
        scope = RetrievalScope(document_id="doc_a_id", version_id="v_b1_id")
        with self.assertRaises(ValueError) as context:
            self.resolver.resolve(scope)
        self.assertIn("does not belong to document", str(context.exception))

    def test_21_scope_resolver_finalized_version_belonging_to_requested_document_accepted(self):
        """Verify valid finalized version belonging to requested document is resolved."""
        scope = RetrievalScope(document_id="doc_b_id", version_id="v_b1_id")
        resolved = self.resolver.resolve(scope)
        self.assertEqual(resolved.version_id, "v_b1_id")
        self.assertEqual(resolved.document_id, "doc_b_id")

    # ─── CONTRACT COMPATIBILITY TESTS ─────────────────────────────

    def test_22_request_validation_success(self):
        """Verify existing valid RetrievalRequest continues to pass validation."""
        req_data = {
            "query": "quantum gravity",
            "scope": {
                "document_id": "doc_a_id",
                "version_id": "v_a2_id",
                "entity_types": ["CONCEPT"],
                "relationship_types": ["EXPLAINS"]
            },
            "options": {
                "top_k": 20,
                "relationship_depth": 2,
                "strategy": "LEXICAL"
            }
        }
        req = RetrievalRequest(**req_data)
        self.assertEqual(req.query, "quantum gravity")
        self.assertEqual(req.scope.document_id, "doc_a_id")
        self.assertEqual(req.options.top_k, 20)

    def test_23_request_validation_invalid_top_k_rejected(self):
        """Verify top_k bounds validation is preserved and enforced."""
        with self.assertRaises(ValidationError):
            RetrievalRequest(
                query="test",
                scope={"document_id": "doc_a_id"},
                options={"top_k": 0}
            )

        with self.assertRaises(ValidationError):
            RetrievalRequest(
                query="test",
                scope={"document_id": "doc_a_id"},
                options={"top_k": 101}
            )

    def test_24_request_validation_invalid_relationship_depth_rejected(self):
        """Verify relationship_depth bounds validation is preserved and enforced."""
        with self.assertRaises(ValidationError):
            RetrievalRequest(
                query="test",
                scope={"document_id": "doc_a_id"},
                options={"relationship_depth": -1}
            )

        with self.assertRaises(ValidationError):
            RetrievalRequest(
                query="test",
                scope={"document_id": "doc_a_id"},
                options={"relationship_depth": 4}
            )

    def test_25_request_validation_document_id_required(self):
        """Verify document_id requirement is enforced under scope."""
        with self.assertRaises(ValidationError):
            RetrievalRequest(
                query="test",
                scope={},  # Missing document_id
            )


if __name__ == "__main__":
    unittest.main()
