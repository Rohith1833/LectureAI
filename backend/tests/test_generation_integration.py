"""
Phase 8E-3D — Integration & Regression Test Suite

Comprehensive end-to-end integration tests verifying all five generation modes:
- QA
- EXPLANATION
- SUMMARY
- COMPARISON
- STUDY_GUIDE

Verifies the complete pipeline:
GenerationRequest -> GenerationService -> RetrievalService -> ContextBuilder
-> GenerationModeStrategy -> PromptBuilder -> LLMProvider -> GroundingValidator
-> GenerationResult

Also verifies API route integration and contract serialization across all modes.
"""

import asyncio
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
from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.schemas.generation import (
    GenerationMode,
    GenerationRequest,
    GenerationResult,
    GenerationOptions,
    ComparisonOptions,
    StudyGuideOptions,
    GroundingStatus,
)
from app.schemas.retrieval import RetrievalScope, RetrievalOptions
from app.services.generation.base import LLMProvider, LLMGenerationRequest, LLMGenerationResponse
from app.services.generation.errors import GroundingValidationError, LLMProviderError
from app.services.generation.generation_service import GenerationService
from app.services.generation.mock_provider import MockLLMProvider
from app.services.retrieval.retrieval_service import RetrievalService


class CustomStructuredMockProvider(LLMProvider):
    """Configurable mock provider returning custom structured data."""

    def __init__(self, structured_output=None, scenario="success", error_message="Provider error"):
        self.structured_output = structured_output
        self.scenario = scenario
        self.error_message = error_message

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
        if self.scenario == "failure":
            raise LLMProviderError(self.error_message)
        if self.scenario == "malformed":
            return LLMGenerationResponse(
                raw_response="not json",
                structured_output=None,
                model_name="mock-malformed",
            )
        return LLMGenerationResponse(
            raw_response="simulated response text",
            structured_output=self.structured_output or {},
            token_usage={"prompt_tokens": 50, "completion_tokens": 25},
            model_name="mock-custom-model",
        )


def _create_test_engine():
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


class TestGenerationIntegrationPipeline(unittest.TestCase):
    """Full-pipeline integration tests for all 5 generation modes."""

    @classmethod
    def setUpClass(cls):
        cls.engine = _create_test_engine()
        cls.TestingSessionLocal = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.TestingSessionLocal()

        # Seed document + approved snapshot + finalized knowledge version + 2 entities
        self.upload_id = str(uuid.uuid4())
        doc = Document(
            id="integ_doc_id",
            upload_id=self.upload_id,
            status="processed",
            extraction_timestamp="2026-08-27T00:00:00Z",
            processing_time=1.0,
            review_state="APPROVED",
        )
        self.db.add(doc)
        self.db.flush()

        snap = AcademicGraphSnapshot(
            id="integ_snap_id",
            upload_id=self.upload_id,
            pipeline_run_id="run_integ",
            approval_version=1,
            approved_revision=1,
            base_graph_fingerprint="bfp",
            resolved_graph_fingerprint="rfp",
            approval_timestamp=time.time(),
            reviewer_id="integ_reviewer",
            nodes=[],
            edges=[],
        )
        self.db.add(snap)
        self.db.flush()

        version = KnowledgeVersion(
            id="integ_v_id",
            upload_id=self.upload_id,
            snapshot_id="integ_snap_id",
            status="BUILDING",
            created_at=time.time(),
        )
        self.db.add(version)
        self.db.flush()

        # Entity 1: Binary Search
        e1 = KnowledgeEntity(
            id="integ_ent_1",
            knowledge_version_id="integ_v_id",
            entity_type="CONCEPT",
            title="Binary Search",
            content="Binary search is a divide-and-conquer algorithm with O(log n) time complexity.",
            stable_id="anc_bs",
        )
        self.db.add(e1)

        # Entity 2: Linear Search
        e2 = KnowledgeEntity(
            id="integ_ent_2",
            knowledge_version_id="integ_v_id",
            entity_type="CONCEPT",
            title="Linear Search",
            content="Linear search scans elements sequentially with O(n) time complexity.",
            stable_id="anc_ls",
        )
        self.db.add(e2)
        self.db.flush()

        version.status = "FINALIZED"
        self.db.commit()

        self.repo = KnowledgeRepository(self.db)
        self.doc_repo = DocumentRepository(self.db)
        self.retrieval_service = RetrievalService(self.repo, self.doc_repo)

    def tearDown(self):
        self.db.close()

    # 1. QA Mode Pipeline
    def test_01_qa_mode_pipeline(self):
        """Verify complete Grounded QA pipeline."""
        qa_data = {
            "answer": "Binary search is O(log n) [S1].",
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "Binary search operates in logarithmic time.",
                    "citation_ids": ["S1"],
                }
            ],
        }
        provider = CustomStructuredMockProvider(structured_output=qa_data)
        service = GenerationService(retrieval_service=self.retrieval_service, provider=provider)

        req = GenerationRequest(
            query="binary search complexity",
            scope=RetrievalScope(document_id="integ_doc_id", version_id="integ_v_id"),
            mode=GenerationMode.QA,
            retrieval_options=RetrievalOptions(top_k=5),
            generation_options=GenerationOptions(temperature=0.0),
        )
        res = asyncio.run(service.generate(req))

        self.assertIsInstance(res, GenerationResult)
        self.assertEqual(res.mode, GenerationMode.QA)
        self.assertEqual(res.overall_grounding_status, GroundingStatus.SUPPORTED)
        self.assertEqual(len(res.claims), 1)
        self.assertIn("S1", res.citations)

    # 2. Explanation Mode Pipeline
    def test_02_explanation_mode_pipeline(self):
        """Verify complete Concept Explanation pipeline."""
        exp_data = {
            "answer": "Binary search works by dividing the search interval in half repeatedly [S1].",
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "Interval is repeatedly divided in half.",
                    "citation_ids": ["S1"],
                }
            ],
        }
        provider = CustomStructuredMockProvider(structured_output=exp_data)
        service = GenerationService(retrieval_service=self.retrieval_service, provider=provider)

        req = GenerationRequest(
            query="explain binary search",
            scope=RetrievalScope(document_id="integ_doc_id", version_id="integ_v_id"),
            mode=GenerationMode.EXPLANATION,
        )
        res = asyncio.run(service.generate(req))

        self.assertEqual(res.mode, GenerationMode.EXPLANATION)
        self.assertEqual(res.overall_grounding_status, GroundingStatus.SUPPORTED)
        self.assertEqual(res.claims[0].grounding_status, GroundingStatus.SUPPORTED)

    # 3. Summary Mode Pipeline
    def test_03_summary_mode_pipeline(self):
        """Verify complete Summary pipeline."""
        summary_data = {
            "answer": "Summary: Binary search is O(log n) and Linear search is O(n) [S1, S2].",
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "Binary search is logarithmic.",
                    "citation_ids": ["S1"],
                },
                {
                    "claim_id": "c2",
                    "text": "Linear search is linear time.",
                    "citation_ids": ["S2"],
                },
            ],
        }
        provider = CustomStructuredMockProvider(structured_output=summary_data)
        service = GenerationService(retrieval_service=self.retrieval_service, provider=provider)

        req = GenerationRequest(
            query="search algorithms summary",
            scope=RetrievalScope(document_id="integ_doc_id", version_id="integ_v_id"),
            mode=GenerationMode.SUMMARY,
        )
        res = asyncio.run(service.generate(req))

        self.assertEqual(res.mode, GenerationMode.SUMMARY)
        self.assertEqual(res.overall_grounding_status, GroundingStatus.SUPPORTED)
        self.assertEqual(len(res.claims), 2)
        self.assertIn("S1", res.citations)
        self.assertIn("S2", res.citations)

    # 4. Comparison Mode Pipeline
    def test_04_comparison_mode_pipeline(self):
        """Verify complete Comparison pipeline with nested citations in dimension values, similarities, and differences."""
        comp_data = {
            "title": "Comparison of Binary Search vs Linear Search",
            "subjects": ["Binary Search", "Linear Search"],
            "comparison_table": [
                {
                    "dimension": "Time Complexity",
                    "values": [
                        {"subject": "Binary Search", "value": "O(log n) [S1]", "citation_ids": ["S1"]},
                        {"subject": "Linear Search", "value": "O(n) [S2]", "citation_ids": ["S2"]},
                    ],
                    "explanation": "Binary search is logarithmic while linear search is linear.",
                }
            ],
            "similarities": [
                {"text": "Both algorithms search for items in a dataset [S1, S2].", "citation_ids": ["S1", "S2"]}
            ],
            "differences": [
                {"text": "Binary search requires sorted input whereas linear search does not [S1].", "citation_ids": ["S1"]}
            ],
        }
        provider = CustomStructuredMockProvider(structured_output=comp_data)
        service = GenerationService(retrieval_service=self.retrieval_service, provider=provider)

        req = GenerationRequest(
            query="compare search algorithms",
            scope=RetrievalScope(document_id="integ_doc_id", version_id="integ_v_id"),
            mode=GenerationMode.COMPARISON,
            comparison_options=ComparisonOptions(
                subjects=["Binary Search", "Linear Search"],
                dimensions=["Time Complexity"],
            ),
        )
        res = asyncio.run(service.generate(req))

        self.assertEqual(res.mode, GenerationMode.COMPARISON)
        self.assertEqual(res.overall_grounding_status, GroundingStatus.SUPPORTED)
        self.assertIsNotNone(res.structured_output)
        self.assertEqual(len(res.structured_output["comparison_table"]), 1)
        self.assertIn("S1", res.citations)
        self.assertIn("S2", res.citations)
        self.assertEqual(res.answer, "Comparison of Binary Search vs Linear Search")

    # 5. Study Guide Mode Pipeline
    def test_05_study_guide_mode_pipeline(self):
        """Verify complete Study Guide pipeline with nested key concepts, review questions, answers, and explanations."""
        guide_data = {
            "title": "Search Algorithms Study Guide",
            "answer": "Comprehensive review of search algorithms in computer science [S1, S2].",
            "key_concepts": [
                {
                    "concept": "Binary Search",
                    "definition": "A divide-and-conquer search algorithm [S1].",
                    "citation_ids": ["S1"],
                },
                {
                    "concept": "Linear Search",
                    "definition": "Sequential scan of an array [S2].",
                    "citation_ids": ["S2"],
                },
            ],
            "learning_objectives": [
                "Understand time complexity differences [S1, S2].",
            ],
            "review_questions": [
                {
                    "question": "What is the time complexity of binary search?",
                    "answer": "O(log n) [S1]",
                    "explanation": "Divides search space by 2 on each step [S1]",
                    "citation_ids": ["S1"],
                }
            ],
            "claims": [
                {"claim_id": "c1", "text": "Binary search is O(log n).", "citation_ids": ["S1"]},
                {"claim_id": "c2", "text": "Linear search is O(n).", "citation_ids": ["S2"]},
            ],
        }
        provider = CustomStructuredMockProvider(structured_output=guide_data)
        service = GenerationService(retrieval_service=self.retrieval_service, provider=provider)

        req = GenerationRequest(
            query="prepare study guide for search",
            scope=RetrievalScope(document_id="integ_doc_id", version_id="integ_v_id"),
            mode=GenerationMode.STUDY_GUIDE,
            study_options=StudyGuideOptions(question_count=4, difficulty="intermediate"),
        )
        res = asyncio.run(service.generate(req))

        self.assertEqual(res.mode, GenerationMode.STUDY_GUIDE)
        self.assertEqual(res.overall_grounding_status, GroundingStatus.SUPPORTED)
        self.assertIsNotNone(res.structured_output)
        self.assertEqual(len(res.structured_output["key_concepts"]), 2)
        self.assertEqual(len(res.structured_output["review_questions"]), 1)
        self.assertIn("S1", res.citations)
        self.assertIn("S2", res.citations)

    # 6. Nested Citation Stripping & Status Rollup (Comparison)
    def test_06_comparison_nested_citation_sanitization(self):
        """Verify invalid citations in nested Comparison output are stripped and result in PARTIALLY_SUPPORTED."""
        comp_data_mixed = {
            "title": "Comparison",
            "subjects": ["Binary Search", "Linear Search"],
            "comparison_table": [
                {
                    "dimension": "Time Complexity",
                    "values": [
                        {"subject": "Binary Search", "value": "O(log n) [S1, S99]", "citation_ids": ["S1", "S99"]},
                    ],
                }
            ],
            "similarities": [],
            "differences": [],
        }
        provider = CustomStructuredMockProvider(structured_output=comp_data_mixed)
        service = GenerationService(retrieval_service=self.retrieval_service, provider=provider)

        req = GenerationRequest(
            query="binary search",
            scope=RetrievalScope(document_id="integ_doc_id", version_id="integ_v_id"),
            mode=GenerationMode.COMPARISON,
            comparison_options=ComparisonOptions(subjects=["A", "B"]),
        )
        res = asyncio.run(service.generate(req))

        # S99 stripped, S1 retained -> PARTIALLY_SUPPORTED
        self.assertEqual(res.overall_grounding_status, GroundingStatus.PARTIALLY_SUPPORTED)
        table = res.structured_output["comparison_table"]
        self.assertEqual(table[0]["values"][0]["citation_ids"], ["S1"])
        self.assertIn("S1", res.citations)
        self.assertNotIn("S99", res.citations)

    # 7. Insufficient Context Detection
    def test_07_insufficient_context_pipeline(self):
        """Verify INSUFFICIENT_CONTEXT marker in structured text rolls up correctly."""
        comp_data_insufficient = {
            "title": "Comparison",
            "subjects": ["Binary Search", "Quantum Search"],
            "comparison_table": [
                {
                    "dimension": "Quantum Speedup",
                    "values": [
                        {"subject": "Quantum Search", "value": "INSUFFICIENT_CONTEXT", "citation_ids": []},
                    ],
                }
            ],
            "similarities": [],
            "differences": [],
        }
        provider = CustomStructuredMockProvider(structured_output=comp_data_insufficient)
        service = GenerationService(retrieval_service=self.retrieval_service, provider=provider)

        req = GenerationRequest(
            query="compare quantum search",
            scope=RetrievalScope(document_id="integ_doc_id", version_id="integ_v_id"),
            mode=GenerationMode.COMPARISON,
            comparison_options=ComparisonOptions(subjects=["Binary Search", "Quantum Search"]),
        )
        res = asyncio.run(service.generate(req))
        self.assertEqual(res.overall_grounding_status, GroundingStatus.INSUFFICIENT_CONTEXT)


class TestGenerationAPIIntegration(unittest.TestCase):
    """Integration tests via FastAPI TestClient on POST /api/v1/generation/query across all 5 modes."""

    @classmethod
    def setUpClass(cls):
        cls.engine = _create_test_engine()
        cls.TestingSessionLocal = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.TestingSessionLocal()

        def override_get_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

        # Seed document and finalized version
        self.upload_id = str(uuid.uuid4())
        doc = Document(
            id="api_integ_doc",
            upload_id=self.upload_id,
            status="processed",
            extraction_timestamp="2026-08-27T00:00:00Z",
            processing_time=1.0,
            review_state="APPROVED",
        )
        self.db.add(doc)
        self.db.flush()

        snap = AcademicGraphSnapshot(
            id="api_integ_snap",
            upload_id=self.upload_id,
            pipeline_run_id="api_integ_run",
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
            id="api_integ_v",
            upload_id=self.upload_id,
            snapshot_id="api_integ_snap",
            status="BUILDING",
            created_at=time.time(),
        )
        self.db.add(version)
        self.db.flush()

        entity = KnowledgeEntity(
            id="api_integ_ent",
            knowledge_version_id="api_integ_v",
            entity_type="CONCEPT",
            title="Binary Search",
            content="Binary search is O(log n).",
            stable_id="anc_api_bs",
        )
        self.db.add(entity)
        self.db.flush()

        version.status = "FINALIZED"
        self.db.commit()

    def tearDown(self):
        self.db.close()
        app.dependency_overrides.clear()

    def _base_payload(self, mode="QA", **kwargs):
        payload = {
            "query": "binary search",
            "scope": {
                "document_id": "api_integ_doc",
                "version_id": "api_integ_v",
            },
            "mode": mode,
            "retrieval_options": {"top_k": 5},
            "generation_options": {"temperature": 0.0, "output_format": "JSON"},
        }
        payload.update(kwargs)
        return payload

    def test_api_qa_mode(self):
        """API POST /generation/query for QA mode returns 200."""
        with patch(
            "app.api.routes.generation._get_provider",
            return_value=MockLLMProvider(scenario="success"),
        ):
            resp = self.client.post("/api/v1/generation/query", json=self._base_payload(mode="QA"))
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["mode"], "QA")
            self.assertEqual(data["overall_grounding_status"], "SUPPORTED")

    def test_api_explanation_mode(self):
        """API POST /generation/query for EXPLANATION mode returns 200."""
        with patch(
            "app.api.routes.generation._get_provider",
            return_value=MockLLMProvider(scenario="success"),
        ):
            resp = self.client.post("/api/v1/generation/query", json=self._base_payload(mode="EXPLANATION"))
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["mode"], "EXPLANATION")

    def test_api_summary_mode(self):
        """API POST /generation/query for SUMMARY mode returns 200."""
        with patch(
            "app.api.routes.generation._get_provider",
            return_value=MockLLMProvider(scenario="success"),
        ):
            resp = self.client.post("/api/v1/generation/query", json=self._base_payload(mode="SUMMARY"))
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["mode"], "SUMMARY")

    def test_api_comparison_mode(self):
        """API POST /generation/query for COMPARISON mode returns 200 + structured_output."""
        comp_output = {
            "title": "Comparison",
            "subjects": ["Binary Search", "Linear Search"],
            "comparison_table": [],
            "similarities": [],
            "differences": [],
        }
        mock_provider = CustomStructuredMockProvider(structured_output=comp_output)
        with patch("app.api.routes.generation._get_provider", return_value=mock_provider):
            payload = self._base_payload(
                mode="COMPARISON",
                comparison_options={"subjects": ["Binary Search", "Linear Search"]},
            )
            resp = self.client.post("/api/v1/generation/query", json=payload)
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["mode"], "COMPARISON")
            self.assertIn("comparison_table", data["structured_output"])

    def test_api_study_guide_mode(self):
        """API POST /generation/query for STUDY_GUIDE mode returns 200 + structured_output."""
        guide_output = {
            "title": "Study Guide",
            "answer": "Overview of study material [S1]",
            "key_concepts": [],
            "learning_objectives": [],
            "review_questions": [],
            "claims": [{"claim_id": "c1", "text": "Statement [S1]", "citation_ids": ["S1"]}],
        }
        mock_provider = CustomStructuredMockProvider(structured_output=guide_output)
        with patch("app.api.routes.generation._get_provider", return_value=mock_provider):
            payload = self._base_payload(
                mode="STUDY_GUIDE",
                study_options={"question_count": 5, "difficulty": "advanced"},
            )
            resp = self.client.post("/api/v1/generation/query", json=payload)
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["mode"], "STUDY_GUIDE")
            self.assertIn("review_questions", data["structured_output"])

    def test_api_comparison_missing_subjects_rejected(self):
        """API POST /generation/query rejects COMPARISON mode without comparison_options."""
        payload = self._base_payload(mode="COMPARISON")
        resp = self.client.post("/api/v1/generation/query", json=payload)
        self.assertEqual(resp.status_code, 422)

    def test_api_study_guide_invalid_options_rejected(self):
        """API POST /generation/query rejects invalid study_options (e.g. invalid difficulty)."""
        payload = self._base_payload(
            mode="STUDY_GUIDE",
            study_options={"question_count": 5, "difficulty": "extreme_difficulty"},
        )
        resp = self.client.post("/api/v1/generation/query", json=payload)
        self.assertEqual(resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()
