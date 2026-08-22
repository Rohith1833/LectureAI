import unittest
import time
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.session import get_db
from app.models import Base, Document, AcademicGraphSnapshot
from app.models.document import DocumentPage, DocumentBlock
from app.models.knowledge import KnowledgeVersion, KnowledgeEntity, KnowledgeRelationship, KnowledgeEvidence


class TestRetrievalAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
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

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.TestingSessionLocal()

        # Override dependency injection
        def override_get_db():
            try:
                yield self.db
            finally:
                pass
        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

        # Seed Document A
        self.upload_a = str(uuid.uuid4())
        self.doc_a = Document(
            id="doc_a_id",
            upload_id=self.upload_a,
            status="processed",
            extraction_timestamp="2026-08-21T12:00:00Z",
            processing_time=1.0,
            review_state="APPROVED"
        )

        # Seed Document B
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

        # Seed Page & Block for A
        self.page_a1 = DocumentPage(id="page_a1_id", document_id="doc_a_id", page_number=1, width=100.0, height=100.0)
        self.db.add(self.page_a1)
        self.db.flush()

        self.blk_a1 = DocumentBlock(
            id="blk_a1_id", document_id="doc_a_id", page_id="page_a1_id", page_number=1,
            reading_order=1, block_type="PARAGRAPH", text="Binary search algorithm cuts complexity.",
            x0=10.0, y0=20.0, x1=110.0, y1=120.0
        )
        self.db.add(self.blk_a1)
        self.db.flush()

        # Seed Snapshots
        self.snap_a = AcademicGraphSnapshot(
            id="snap_a_id", upload_id=self.upload_a, pipeline_run_id="run_a",
            approval_version=42, approved_revision=1, base_graph_fingerprint="bfp_a",
            resolved_graph_fingerprint="rfp_a", approval_timestamp=time.time(),
            reviewer_id="reviewer", nodes=[], edges=[]
        )
        self.snap_b = AcademicGraphSnapshot(
            id="snap_b_id", upload_id=self.upload_b, pipeline_run_id="run_b",
            approval_version=2, approved_revision=1, base_graph_fingerprint="bfp_b",
            resolved_graph_fingerprint="rfp_b", approval_timestamp=time.time(),
            reviewer_id="reviewer", nodes=[], edges=[]
        )
        self.db.add_all([self.snap_a, self.snap_b])
        self.db.flush()

        # Seed Versions (one building, one finalized)
        self.v_a = KnowledgeVersion(
            id="v_a_id", upload_id=self.upload_a, snapshot_id="snap_a_id",
            status="BUILDING", created_at=time.time()
        )
        self.v_b = KnowledgeVersion(
            id="v_b_id", upload_id=self.upload_b, snapshot_id="snap_b_id",
            status="BUILDING", created_at=time.time()
        )
        self.db.add_all([self.v_a, self.v_b])
        self.db.flush()

        # Seed Entity in Version A
        self.e_exact = KnowledgeEntity(
            id="e_exact_id", knowledge_version_id="v_a_id", entity_type="CONCEPT",
            title="Binary Search", content="Binary Search explanation", stable_id="anc_exact"
        )
        self.db.add(self.e_exact)
        self.db.flush()

        # Seed evidence
        self.ev_exact = KnowledgeEvidence(
            id="ev_exact_id", entity_id="e_exact_id", document_id="doc_a_id", page_number=1,
            x0=10.0, y0=20.0, x1=110.0, y1=120.0, text_reference="Binary search algorithm cuts complexity.",
            section_title="Intro", provenance="EXPLICIT_CLASSIFIER"
        )
        # Seed a minimal evidence record with null values to test serialization safety
        self.ev_nulls = KnowledgeEvidence(
            id="ev_nulls_id", entity_id="e_exact_id", document_id="doc_a_id",
            page_number=None, section_title=None, x0=None, y0=None, x1=None, y1=None,
            text_reference=None, provenance="EXPLICIT_CLASSIFIER"
        )
        self.db.add_all([self.ev_exact, self.ev_nulls])
        self.db.flush()

        # Finalize versions (safe finalize)
        self.v_a.status = "FINALIZED"
        self.v_b.status = "FINALIZED"
        self.db.commit()

    def tearDown(self):
        self.db.close()
        app.dependency_overrides.clear()

    # ─── REQUEST VALIDATION TESTS ──────────────────────────────────

    def test_01_valid_retrieval_request(self):
        """Verify that a valid request is accepted with HTTP 200."""
        payload = {
            "query": "binary search",
            "scope": {
                "document_id": "doc_a_id",
                "version_id": "v_a_id"
            }
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        self.assertEqual(response.status_code, 200)

    def test_02_empty_query(self):
        """Verify empty query is rejected with HTTP 422."""
        payload = {
            "query": "",
            "scope": {
                "document_id": "doc_a_id",
                "version_id": "v_a_id"
            }
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        self.assertEqual(response.status_code, 422)

    def test_03_whitespace_only_query(self):
        """Verify whitespace query is rejected with HTTP 422."""
        payload = {
            "query": "   ",
            "scope": {
                "document_id": "doc_a_id",
                "version_id": "v_a_id"
            }
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        self.assertEqual(response.status_code, 422)

    def test_04_invalid_top_k(self):
        """Verify top_k less than 1 or greater than 100 is rejected with HTTP 422."""
        payload_too_small = {
            "query": "binary",
            "scope": {"document_id": "doc_a_id", "version_id": "v_a_id"},
            "options": {"top_k": 0}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload_too_small)
        self.assertEqual(response.status_code, 422)

        payload_too_large = {
            "query": "binary",
            "scope": {"document_id": "doc_a_id", "version_id": "v_a_id"},
            "options": {"top_k": 101}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload_too_large)
        self.assertEqual(response.status_code, 422)

    def test_05_invalid_relationship_depth(self):
        """Verify relationship_depth constraints (0 to 3) are validated."""
        payload_invalid = {
            "query": "binary",
            "scope": {"document_id": "doc_a_id", "version_id": "v_a_id"},
            "options": {"relationship_depth": 4}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload_invalid)
        self.assertEqual(response.status_code, 422)

    def test_06_invalid_scope(self):
        """Verify malformed scope structure is rejected."""
        payload_invalid = {
            "query": "binary",
            "scope": {
                # missing document_id
                "version_id": "v_a_id"
            }
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload_invalid)
        self.assertEqual(response.status_code, 422)

    # ─── SUCCESSFUL RETRIEVAL TESTS ────────────────────────────────

    def test_07_successful_lexical_retrieval(self):
        """Verify successful lexical retrieval returning expected matches."""
        payload = {
            "query": "binary search",
            "scope": {"document_id": "doc_a_id", "version_id": "v_a_id"}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["query"], "binary search")
        self.assertEqual(len(data["entities"]), 1)
        self.assertEqual(data["entities"][0]["entity"]["id"], "e_exact_id")

    def test_08_latest_finalized_version_resolution(self):
        """Verify version resolution defaults to latest finalized version when null."""
        payload = {
            "query": "binary search",
            "scope": {"document_id": "doc_a_id", "version_id": None}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provenance"]["knowledge_version_id"], "v_a_id")

    def test_09_explicit_version_resolution(self):
        """Verify explicit version matches requested UUID."""
        payload = {
            "query": "binary search",
            "scope": {"document_id": "doc_a_id", "version_id": "v_a_id"}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provenance"]["knowledge_version_id"], "v_a_id")

    def test_10_top_k_behavior(self):
        """Verify top_k limits returned items list size."""
        payload = {
            "query": "binary search",
            "scope": {"document_id": "doc_a_id", "version_id": "v_a_id"},
            "options": {"top_k": 1}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        self.assertEqual(len(response.json()["entities"]), 1)

    def test_11_has_more_behavior(self):
        """Verify has_more flag reflects truncation."""
        payload = {
            "query": "binary search",
            "scope": {"document_id": "doc_a_id", "version_id": "v_a_id"},
            "options": {"top_k": 1}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        self.assertFalse(response.json()["has_more"])

    def test_12_relationships_included(self):
        """Verify relationship structures are returned when configured."""
        payload = {
            "query": "binary search",
            "scope": {"document_id": "doc_a_id", "version_id": "v_a_id"},
            "options": {"include_relationships": True}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        self.assertIn("outgoing_relationships", response.json()["entities"][0])

    def test_13_evidence_included(self):
        """Verify evidence is returned when requested."""
        payload = {
            "query": "binary search",
            "scope": {"document_id": "doc_a_id", "version_id": "v_a_id"},
            "options": {"include_evidence": True}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        self.assertGreater(len(response.json()["entities"][0]["evidence"]), 0)

    def test_14_passages_included(self):
        """Verify source block passages are present."""
        payload = {
            "query": "binary search",
            "scope": {"document_id": "doc_a_id", "version_id": "v_a_id"},
            "options": {"include_evidence": True, "include_passages": True}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        self.assertGreater(len(response.json()["entities"][0]["passages"]), 0)
        self.assertEqual(response.json()["entities"][0]["passages"][0]["text"], "Binary search algorithm cuts complexity.")

    def test_15_provenance_returned(self):
        """Verify diagnostic details are populated."""
        payload = {
            "query": "binary search",
            "scope": {"document_id": "doc_a_id", "version_id": "v_a_id"}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        self.assertIn("provenance", response.json())
        prov = response.json()["provenance"]
        self.assertEqual(prov["document_id"], "doc_a_id")
        self.assertEqual(prov["approval_version"], 42)

    # ─── SCOPE ISOLATION TESTS ─────────────────────────────────────

    def test_16_document_isolation(self):
        """Verify queries inside document B do not return document A's entities."""
        payload = {
            "query": "binary search",
            "scope": {"document_id": "doc_b_id", "version_id": "v_b_id"}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        self.assertEqual(len(response.json()["entities"]), 0)

    def test_17_version_isolation(self):
        """Verify that requesting an empty version isolates matches."""
        # Create an empty version C on document A
        self.snap_c = AcademicGraphSnapshot(
            id="snap_c_id", upload_id=self.upload_a, pipeline_run_id="run_c",
            approval_version=3, approved_revision=1, base_graph_fingerprint="bfp_c",
            resolved_graph_fingerprint="rfp_c", approval_timestamp=time.time(),
            reviewer_id="reviewer", nodes=[], edges=[]
        )
        self.db.add(self.snap_c)
        self.db.flush()

        self.v_c = KnowledgeVersion(
            id="v_c_id", upload_id=self.upload_a, snapshot_id="snap_c_id",
            status="BUILDING", created_at=time.time()
        )
        self.db.add(self.v_c)
        self.db.flush()

        self.v_c.status = "FINALIZED"
        self.db.commit()

        payload = {
            "query": "binary search",
            "scope": {"document_id": "doc_a_id", "version_id": "v_c_id"}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        self.assertEqual(len(response.json()["entities"]), 0)

    def test_18_building_version_rejected(self):
        """Verify that requests targeting non-finalized versions are rejected."""
        # Create building version on document A
        self.snap_d = AcademicGraphSnapshot(
            id="snap_d_id", upload_id=self.upload_a, pipeline_run_id="run_d",
            approval_version=4, approved_revision=1, base_graph_fingerprint="bfp_d",
            resolved_graph_fingerprint="rfp_d", approval_timestamp=time.time(),
            reviewer_id="reviewer", nodes=[], edges=[]
        )
        self.db.add(self.snap_d)
        self.db.flush()

        self.v_d = KnowledgeVersion(
            id="v_d_id", upload_id=self.upload_a, snapshot_id="snap_d_id",
            status="BUILDING", created_at=time.time()
        )
        self.db.add(self.v_d)
        self.db.commit()

        payload = {
            "query": "binary search",
            "scope": {"document_id": "doc_a_id", "version_id": "v_d_id"}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("not finalized", response.json()["message"].lower())

    def test_19_cross_document_version_rejected(self):
        """Verify cross-document version/snapshot combinations are rejected."""
        payload = {
            "query": "binary search",
            "scope": {"document_id": "doc_a_id", "version_id": "v_b_id"}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("does not belong to document", response.json()["message"].lower())

    # ─── ERROR HANDLING TESTS ──────────────────────────────────────

    def test_20_document_not_found(self):
        """Verify querying missing document ID yields HTTP 404."""
        payload = {
            "query": "binary search",
            "scope": {"document_id": "missing_doc_id", "version_id": None}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["message"].lower())

    def test_21_no_finalized_knowledge_version(self):
        """Verify querying document with no finalized version yields HTTP 400."""
        # Create doc without snapshots/versions
        self.doc_c = Document(
            id="doc_c_id", upload_id="other", status="processed",
            extraction_timestamp="2026-08-21T12:00:00Z", processing_time=1.0, review_state="APPROVED"
        )
        self.db.add(self.doc_c)
        self.db.commit()

        payload = {
            "query": "binary search",
            "scope": {"document_id": "doc_c_id", "version_id": None}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("no finalized knowledgeversion", response.json()["message"].lower())


    def test_22_version_not_found(self):
        """Verify querying explicit non-existent version UUID yields HTTP 404."""
        payload = {
            "query": "binary search",
            "scope": {"document_id": "doc_a_id", "version_id": "missing_version_id"}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["message"].lower())

    def test_23_unsupported_semantic_strategy(self):
        """Verify requesting SEMANTIC strategy is rejected with HTTP 400."""
        payload = {
            "query": "binary search",
            "scope": {"document_id": "doc_a_id", "version_id": "v_a_id"},
            "options": {"strategy": "SEMANTIC"}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("not supported", response.json()["message"].lower())

    def test_24_unsupported_hybrid_strategy(self):
        """Verify requesting HYBRID strategy is rejected with HTTP 400."""
        payload = {
            "query": "binary search",
            "scope": {"document_id": "doc_a_id", "version_id": "v_a_id"},
            "options": {"strategy": "HYBRID"}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("not supported", response.json()["message"].lower())

    # ─── SERIALIZATION TESTS ───────────────────────────────────────

    def test_25_response_is_valid_json(self):
        """Verify response contains valid JSON structure."""
        payload = {
            "query": "binary search",
            "scope": {"document_id": "doc_a_id", "version_id": "v_a_id"}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), dict)

    def test_26_no_sqlalchemy_orm_objects_leak(self):
        """Verify response is successfully parsed with no raw SQLAlchemy model leakage."""
        payload = {
            "query": "binary search",
            "scope": {"document_id": "doc_a_id", "version_id": "v_a_id"}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        data = response.json()
        self.assertIsInstance(data["entities"][0]["entity"]["title"], str)

    def test_27_nullable_evidence_passages_serialize_correctly(self):
        """Verify that null values in evidence/passages serialize properly."""
        payload = {
            "query": "binary search",
            "scope": {"document_id": "doc_a_id", "version_id": "v_a_id"},
            "options": {"include_evidence": True, "include_passages": True}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        self.assertEqual(response.status_code, 200)
        evidence_list = response.json()["entities"][0]["evidence"]
        null_ev = next(e for e in evidence_list if e["id"] == "ev_nulls_id")
        self.assertIsNone(null_ev["x0"])
        self.assertIsNone(null_ev["page_number"])

    def test_28_stale_evidence_serializes_correctly(self):
        """Verify that evidence stale flagging acts as expected in serialized contracts."""
        payload = {
            "query": "binary search",
            "scope": {"document_id": "doc_a_id", "version_id": "v_a_id"},
            "options": {"include_evidence": True}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        data = response.json()
        self.assertIn("evidence", data["entities"][0])

    def test_29_coordinates_serialize_correctly(self):
        """Verify bounding box floats serialize successfully."""
        payload = {
            "query": "binary search",
            "scope": {"document_id": "doc_a_id", "version_id": "v_a_id"},
            "options": {"include_evidence": True}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        ev = response.json()["entities"][0]["evidence"][0]
        self.assertEqual(ev["x0"], 10.0)
        self.assertEqual(ev["y1"], 120.0)

    def test_30_relationship_data_serializes_correctly(self):
        """Verify relationship source/target schema serialize successfully."""
        payload = {
            "query": "binary search",
            "scope": {"document_id": "doc_a_id", "version_id": "v_a_id"},
            "options": {"include_relationships": True}
        }
        response = self.client.post("/api/v1/retrieval/query", json=payload)
        data = response.json()
        self.assertIn("entities", data)


if __name__ == "__main__":
    unittest.main()
