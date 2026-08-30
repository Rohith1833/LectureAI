"""
Phase 8D — Generation API endpoint tests.

Uses FastAPI TestClient with in-memory SQLite and patches _get_provider()
to inject MockLLMProvider, ensuring no real Groq calls are made.
"""

import time
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.session import get_db
from app.models import Base, Document, AcademicGraphSnapshot
from app.models.knowledge import KnowledgeVersion, KnowledgeEntity
from app.services.generation.errors import GroundingValidationError, LLMProviderError
from app.services.generation.mock_provider import MockLLMProvider


def _make_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return engine


class TestGenerationAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = _make_engine()
        cls.TestingSessionLocal = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.TestingSessionLocal()

        # Inject DB override
        def override_get_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

        # Seed minimal document + version
        self.upload_id = str(uuid.uuid4())
        doc = Document(
            id="api_doc_id",
            upload_id=self.upload_id,
            status="processed",
            extraction_timestamp="2026-08-23T00:00:00Z",
            processing_time=1.0,
            review_state="APPROVED",
        )
        self.db.add(doc)
        self.db.flush()

        snap = AcademicGraphSnapshot(
            id="api_snap_id",
            upload_id=self.upload_id,
            pipeline_run_id="api_run",
            approval_version=1,
            approved_revision=1,
            base_graph_fingerprint="bfp",
            resolved_graph_fingerprint="rfp",
            approval_timestamp=time.time(),
            reviewer_id="test",
            nodes=[],
            edges=[],
        )
        self.db.add(snap)
        self.db.flush()

        version = KnowledgeVersion(
            id="api_v_id",
            upload_id=self.upload_id,
            snapshot_id="api_snap_id",
            status="BUILDING",
            created_at=time.time(),
        )
        self.db.add(version)
        self.db.flush()

        entity = KnowledgeEntity(
            id="api_ent_id",
            knowledge_version_id="api_v_id",
            entity_type="CONCEPT",
            title="Binary Search",
            content="Binary search runs in O(log n).",
            stable_id="anc_binary_api",
        )
        self.db.add(entity)
        self.db.flush()

        # Finalize the version to permit retrieval queries
        version.status = "FINALIZED"
        self.db.commit()

    def tearDown(self):
        self.db.close()
        app.dependency_overrides.clear()

    # ---------------------------------------------------------------------- #
    # Shared valid request body                                                #
    # ---------------------------------------------------------------------- #

    def _valid_body(self, query: str = "binary search") -> dict:
        return {
            "query": query,
            "scope": {
                "document_id": "api_doc_id",
                "version_id": "api_v_id",
            },
            "retrieval_options": {
                "top_k": 5,
                "include_relationships": False,
                "include_evidence": False,
                "include_passages": False,
                "relationship_depth": 0,
                "strategy": "LEXICAL",
            },
            "generation_options": {
                "temperature": 0.0,
                "output_format": "TEXT",
            },
        }

    # ---------------------------------------------------------------------- #
    # Tests                                                                    #
    # ---------------------------------------------------------------------- #

    def test_01_successful_generation(self):
        """POST /generation/query with mock provider returns 200 + GenerationResult."""
        with patch(
            "app.api.routes.generation._get_provider",
            return_value=MockLLMProvider(scenario="success"),
        ):
            response = self.client.post("/api/v1/generation/query", json=self._valid_body())

        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertIn("answer", data)
        self.assertIn("claims", data)
        self.assertIn("citations", data)
        self.assertIn("overall_grounding_status", data)
        self.assertIn("model_metadata", data)

    def test_02_empty_query_returns_422(self):
        """Empty query string must be rejected by Pydantic validation (422)."""
        body = self._valid_body(query="   ")
        with patch(
            "app.api.routes.generation._get_provider",
            return_value=MockLLMProvider(scenario="success"),
        ):
            response = self.client.post("/api/v1/generation/query", json=body)
        self.assertEqual(response.status_code, 422)

    def test_03_unknown_document_returns_404(self):
        """Unknown document_id in scope → 404."""
        body = self._valid_body()
        body["scope"]["document_id"] = "nonexistent_doc"
        body["scope"]["version_id"] = None
        with patch(
            "app.api.routes.generation._get_provider",
            return_value=MockLLMProvider(scenario="success"),
        ):
            response = self.client.post("/api/v1/generation/query", json=body)
        self.assertEqual(response.status_code, 404)

    def test_04_provider_failure_returns_502(self):
        """LLMProviderError from provider → 502 Bad Gateway."""
        with patch(
            "app.api.routes.generation._get_provider",
            return_value=MockLLMProvider(scenario="provider_failure"),
        ):
            response = self.client.post("/api/v1/generation/query", json=self._valid_body())
        self.assertEqual(response.status_code, 502)
        self.assertIn("AI service error", response.json()["message"])

    def test_05_grounding_validation_failure_returns_422(self):
        """GroundingValidationError from validator → 422."""
        with patch(
            "app.api.routes.generation._get_provider",
            return_value=MockLLMProvider(scenario="malformed_output"),
        ):
            response = self.client.post("/api/v1/generation/query", json=self._valid_body())
        self.assertEqual(response.status_code, 422)
        self.assertIn("validation", response.json()["message"].lower())

    def test_06_response_schema_complete(self):
        """All GenerationResult fields must be present in the response."""
        with patch(
            "app.api.routes.generation._get_provider",
            return_value=MockLLMProvider(scenario="success"),
        ):
            response = self.client.post("/api/v1/generation/query", json=self._valid_body())

        self.assertEqual(response.status_code, 200)
        data = response.json()
        required_fields = {"answer", "claims", "citations", "overall_grounding_status", "model_metadata"}
        self.assertTrue(required_fields.issubset(data.keys()), f"Missing fields: {required_fields - data.keys()}")

    def test_07_insufficient_context_returns_200(self):
        """INSUFFICIENT_CONTEXT grounding status is a valid result — must return 200."""
        from app.services.generation.base import LLMGenerationResponse

        class InsufficientProvider:
            async def generate(self, request):
                return LLMGenerationResponse(
                    raw_response="INSUFFICIENT_CONTEXT",
                    structured_output={"answer": "INSUFFICIENT_CONTEXT: No data.", "claims": []},
                    model_name="mock-insufficient",
                )

        with patch(
            "app.api.routes.generation._get_provider",
            return_value=InsufficientProvider(),
        ):
            response = self.client.post("/api/v1/generation/query", json=self._valid_body())

        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["overall_grounding_status"], "INSUFFICIENT_CONTEXT")

    def test_08_mock_provider_no_real_groq_calls(self):
        """Confirm the Groq SDK is never contacted during API tests."""
        groq_import_path = "app.services.generation.groq_provider.AsyncGroq"
        with patch(groq_import_path) as mock_groq_cls:
            with patch(
                "app.api.routes.generation._get_provider",
                return_value=MockLLMProvider(scenario="success"),
            ):
                response = self.client.post("/api/v1/generation/query", json=self._valid_body())

        self.assertEqual(response.status_code, 200)
        mock_groq_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
