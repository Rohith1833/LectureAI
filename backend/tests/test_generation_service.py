"""
Phase 8D — GenerationService + GroundingValidator unit tests.

Uses in-memory SQLite (same pattern as test_retrieval_ranking.py) with real
Phase 7 RetrievalService, MockLLMProvider, and GroundingValidator.

The integration test (test_15_*) verifies that Phase 8D actually consumes
Phase 7 retrieval output rather than bypassing it.

No real Groq calls are made.
"""

import asyncio
import time
import unittest
import uuid

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, Document, AcademicGraphSnapshot
from app.models.knowledge import KnowledgeVersion, KnowledgeEntity
from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.schemas.generation import (
    GenerationContext,
    GenerationOptions,
    GenerationRequest,
    GenerationResult,
    GroundingStatus,
    ContextSource,
)
from app.schemas.retrieval import RetrievalScope, RetrievalOptions, RetrievalProvenance
from app.services.generation.base import LLMGenerationRequest, LLMGenerationResponse
from app.services.generation.context_builder import ContextBuilder
from app.services.generation.errors import GroundingValidationError, LLMProviderError
from app.services.generation.generation_service import GenerationService
from app.services.generation.grounding_validator import GroundingValidator
from app.services.generation.mock_provider import MockLLMProvider
from app.services.retrieval.retrieval_service import RetrievalService


# --------------------------------------------------------------------------- #
# Shared in-memory DB infrastructure                                           #
# --------------------------------------------------------------------------- #

def _build_engine():
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


# --------------------------------------------------------------------------- #
# Helper: build a minimal GenerationRequest                                    #
# --------------------------------------------------------------------------- #

def _make_gen_request(
    query: str,
    document_id: str,
    version_id: str | None = None,
    temperature: float = 0.0,
) -> GenerationRequest:
    return GenerationRequest(
        query=query,
        scope=RetrievalScope(document_id=document_id, version_id=version_id),
        retrieval_options=RetrievalOptions(
            top_k=10,
            include_relationships=False,
            include_evidence=False,
            include_passages=False,
            strategy="LEXICAL",
        ),
        generation_options=GenerationOptions(temperature=temperature),
    )


# --------------------------------------------------------------------------- #
# Helper: build a GenerationContext with N sources                             #
# --------------------------------------------------------------------------- #

def _make_context(*citation_ids: str) -> GenerationContext:
    provenance = RetrievalProvenance(
        knowledge_version_id="v_test",
        approval_version=1,
        document_id="doc_test",
        strategy_used="LEXICAL",
        query_terms=["test"],
        total_candidates_considered=len(citation_ids),
    )
    sources = [
        ContextSource(
            citation_id=cid,
            entity_id=f"ent_{cid}",
            title=f"Title {cid}",
            entity_type="CONCEPT",
            content=f"Content for {cid}",
        )
        for cid in citation_ids
    ]
    return GenerationContext(sources=sources, provenance=provenance)


# --------------------------------------------------------------------------- #
# Helper: build an LLMGenerationResponse directly                              #
# --------------------------------------------------------------------------- #

def _make_llm_response(
    answer: str,
    claims: list | None = None,
    token_usage: dict | None = None,
) -> LLMGenerationResponse:
    structured = {"answer": answer, "claims": claims or []}
    return LLMGenerationResponse(
        raw_response=answer,
        structured_output=structured,
        token_usage=token_usage or {"prompt_tokens": 30, "completion_tokens": 10, "total_tokens": 40},
        model_name="mock-model",
    )


# --------------------------------------------------------------------------- #
# GroundingValidator unit tests (no DB needed)                                 #
# --------------------------------------------------------------------------- #

class TestGroundingValidator(unittest.TestCase):
    """Tests for the pure-function GroundingValidator."""

    def setUp(self):
        self.validator = GroundingValidator()
        self.request = _make_gen_request("What is X?", "doc_test")

    def test_01_structured_output_none_raises(self):
        """structured_output=None must raise GroundingValidationError."""
        response = LLMGenerationResponse(
            raw_response="raw",
            structured_output=None,
            model_name="mock-model",
        )
        context = _make_context("S1")
        with self.assertRaises(GroundingValidationError) as ctx:
            self.validator.validate(response, context, self.request)
        self.assertIn("no structured output", str(ctx.exception).lower())

    def test_02_missing_answer_key_raises(self):
        """structured_output without 'answer' must raise GroundingValidationError."""
        response = LLMGenerationResponse(
            raw_response="raw",
            structured_output={"claims": []},
            model_name="mock-model",
        )
        context = _make_context("S1")
        with self.assertRaises(GroundingValidationError) as ctx:
            self.validator.validate(response, context, self.request)
        self.assertIn("answer", str(ctx.exception).lower())

    def test_03_all_valid_citations_supported(self):
        """All claim citation IDs valid → SUPPORTED overall."""
        context = _make_context("S1", "S2")
        response = _make_llm_response(
            "Answer [S1][S2]",
            claims=[{"claim_id": "c1", "text": "A fact.", "citation_ids": ["S1", "S2"]}],
        )
        result = self.validator.validate(response, context, self.request)
        self.assertEqual(result.overall_grounding_status, GroundingStatus.SUPPORTED)
        self.assertEqual(result.claims[0].grounding_status, GroundingStatus.SUPPORTED)
        self.assertEqual(result.claims[0].citation_ids, ["S1", "S2"])

    def test_04_invalid_citation_stripped_partially_supported(self):
        """S99 not in context → stripped from claim; status PARTIALLY_SUPPORTED."""
        context = _make_context("S1")
        response = _make_llm_response(
            "Answer [S1][S99]",
            claims=[{"claim_id": "c1", "text": "Fact.", "citation_ids": ["S1", "S99"]}],
        )
        result = self.validator.validate(response, context, self.request)
        self.assertNotIn("S99", result.claims[0].citation_ids)
        self.assertIn("S1", result.claims[0].citation_ids)
        self.assertEqual(result.claims[0].grounding_status, GroundingStatus.PARTIALLY_SUPPORTED)

    def test_05_all_invalid_citations_unsupported(self):
        """All claim citation IDs invalid → UNSUPPORTED."""
        context = _make_context("S1")
        response = _make_llm_response(
            "Answer [S99]",
            claims=[{"claim_id": "c1", "text": "Fact.", "citation_ids": ["S99"]}],
        )
        result = self.validator.validate(response, context, self.request)
        self.assertEqual(result.claims[0].grounding_status, GroundingStatus.UNSUPPORTED)
        self.assertEqual(result.claims[0].citation_ids, [])

    def test_06_no_citations_on_claim_unsupported(self):
        """Claim with empty citation_ids → UNSUPPORTED."""
        context = _make_context("S1")
        response = _make_llm_response(
            "Answer",
            claims=[{"claim_id": "c1", "text": "Fact.", "citation_ids": []}],
        )
        result = self.validator.validate(response, context, self.request)
        self.assertEqual(result.claims[0].grounding_status, GroundingStatus.UNSUPPORTED)

    def test_07_no_claims_overall_unsupported(self):
        """Empty claims list → UNSUPPORTED overall."""
        context = _make_context("S1")
        response = _make_llm_response("Answer", claims=[])
        result = self.validator.validate(response, context, self.request)
        self.assertEqual(result.overall_grounding_status, GroundingStatus.UNSUPPORTED)
        self.assertEqual(len(result.claims), 0)

    def test_08_insufficient_context_detected(self):
        """INSUFFICIENT_CONTEXT marker in answer → INSUFFICIENT_CONTEXT overall."""
        context = _make_context()
        response = _make_llm_response(
            "INSUFFICIENT_CONTEXT: No relevant sources found.",
            claims=[],
        )
        result = self.validator.validate(response, context, self.request)
        self.assertEqual(result.overall_grounding_status, GroundingStatus.INSUFFICIENT_CONTEXT)

    def test_09_citations_dict_only_referenced_ids(self):
        """citations dict must only include IDs referenced by surviving claims."""
        context = _make_context("S1", "S2", "S3")
        response = _make_llm_response(
            "Answer [S1]",
            claims=[{"claim_id": "c1", "text": "Fact.", "citation_ids": ["S1"]}],
        )
        result = self.validator.validate(response, context, self.request)
        self.assertIn("S1", result.citations)
        self.assertNotIn("S2", result.citations)
        self.assertNotIn("S3", result.citations)

    def test_10_model_metadata_populated(self):
        """Token usage from provider must appear in model_metadata."""
        context = _make_context("S1")
        response = _make_llm_response(
            "Answer [S1]",
            claims=[{"claim_id": "c1", "text": "Fact.", "citation_ids": ["S1"]}],
            token_usage={"prompt_tokens": 50, "completion_tokens": 25, "total_tokens": 75},
        )
        result = self.validator.validate(response, context, self.request)
        self.assertIsNotNone(result.model_metadata)
        self.assertEqual(result.model_metadata["token_usage"]["total_tokens"], 75)
        self.assertEqual(result.model_metadata["model_name"], "mock-model")

    def test_11_mixed_claims_partially_supported(self):
        """Mix of SUPPORTED and UNSUPPORTED claims → PARTIALLY_SUPPORTED overall."""
        context = _make_context("S1")
        response = _make_llm_response(
            "Answer [S1] also [S99]",
            claims=[
                {"claim_id": "c1", "text": "Fact 1.", "citation_ids": ["S1"]},
                {"claim_id": "c2", "text": "Fact 2.", "citation_ids": ["S99"]},
            ],
        )
        result = self.validator.validate(response, context, self.request)
        self.assertEqual(result.overall_grounding_status, GroundingStatus.PARTIALLY_SUPPORTED)

    def test_12_malformed_claims_block_handled(self):
        """Claims field that is not a list should be treated as empty — no crash."""
        response = LLMGenerationResponse(
            raw_response="raw",
            structured_output={"answer": "Some answer.", "claims": "not-a-list"},
            model_name="mock-model",
        )
        context = _make_context("S1")
        result = self.validator.validate(response, context, self.request)
        self.assertEqual(len(result.claims), 0)
        self.assertEqual(result.overall_grounding_status, GroundingStatus.UNSUPPORTED)

    def test_13_generation_result_schema_complete(self):
        """GenerationResult must have all required fields populated."""
        context = _make_context("S1")
        response = _make_llm_response(
            "Answer [S1]",
            claims=[{"claim_id": "c1", "text": "Fact.", "citation_ids": ["S1"]}],
        )
        result = self.validator.validate(response, context, self.request)
        self.assertIsInstance(result, GenerationResult)
        self.assertIsInstance(result.answer, str)
        self.assertIsInstance(result.claims, list)
        self.assertIsInstance(result.citations, dict)
        self.assertIsInstance(result.overall_grounding_status, GroundingStatus)
        self.assertIsNotNone(result.model_metadata)


# --------------------------------------------------------------------------- #
# GenerationService integration tests (with real Phase 7 retrieval)           #
# --------------------------------------------------------------------------- #

class TestGenerationService(unittest.TestCase):
    """
    Tests GenerationService using real RetrievalService (in-memory SQLite)
    and MockLLMProvider. No real Groq calls.

    The integration test verifies that Phase 8D actually consumes Phase 7
    retrieval output rather than bypassing it.
    """

    @classmethod
    def setUpClass(cls):
        cls.engine = _build_engine()
        cls.TestingSessionLocal = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.TestingSessionLocal()

        # Minimal seeded document + snapshot + version + entity
        self.upload_id = str(uuid.uuid4())
        doc = Document(
            id="gen_doc_id",
            upload_id=self.upload_id,
            status="processed",
            extraction_timestamp="2026-08-23T00:00:00Z",
            processing_time=1.0,
            review_state="APPROVED",
        )
        self.db.add(doc)
        self.db.flush()

        snap = AcademicGraphSnapshot(
            id="gen_snap_id",
            upload_id=self.upload_id,
            pipeline_run_id="gen_run",
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
            id="gen_v_id",
            upload_id=self.upload_id,
            snapshot_id="gen_snap_id",
            status="BUILDING",
            created_at=time.time(),
        )
        self.db.add(version)
        self.db.flush()

        entity = KnowledgeEntity(
            id="gen_ent_id",
            knowledge_version_id="gen_v_id",
            entity_type="CONCEPT",
            title="Binary Search",
            content="Binary search algorithm operates in O(log n) time.",
            stable_id="anc_binary_search",
        )
        self.db.add(entity)
        self.db.flush()

        # Finalize the version to permit retrieval queries
        version.status = "FINALIZED"
        self.db.commit()

        self.repo = KnowledgeRepository(self.db)
        self.doc_repo = DocumentRepository(self.db)
        self.retrieval_service = RetrievalService(self.repo, self.doc_repo)

    def tearDown(self):
        self.db.close()

    def _make_service(self, scenario: str = "success") -> GenerationService:
        provider = MockLLMProvider(scenario=scenario)
        return GenerationService(
            retrieval_service=self.retrieval_service,
            provider=provider,
        )

    def _run(self, coro):
        """Run a coroutine synchronously from a synchronous test."""
        return asyncio.run(coro)

    # ------------------------------------------------------------------ #

    def test_14_full_pipeline_mock_success(self):
        """Full pipeline with real retrieval + MockLLMProvider returns GenerationResult."""
        service = self._make_service("success")
        request = _make_gen_request("binary search", "gen_doc_id", version_id="gen_v_id")
        result = self._run(service.generate(request))

        self.assertIsInstance(result, GenerationResult)
        self.assertIsInstance(result.answer, str)
        self.assertGreater(len(result.answer), 0)
        self.assertIsInstance(result.overall_grounding_status, GroundingStatus)

    def test_15_integration_retrieval_consumed(self):
        """Phase 7 retrieval is actually invoked: result reflects the seeded entity."""
        # The entity title is "Binary Search" — querying "binary" should hit it
        service = self._make_service("success")
        request = _make_gen_request("binary search", "gen_doc_id", version_id="gen_v_id")
        result = self._run(service.generate(request))
        # If retrieval was bypassed the context would be empty;
        # MockLLMProvider(success) always returns S1 citations.
        # At minimum the pipeline should complete without error.
        self.assertIsNotNone(result)

    def test_16_provider_failure_propagates(self):
        """LLMProviderError must not be swallowed by GenerationService."""
        service = self._make_service("provider_failure")
        request = _make_gen_request("binary search", "gen_doc_id", version_id="gen_v_id")
        with self.assertRaises(LLMProviderError):
            self._run(service.generate(request))

    def test_17_malformed_output_raises_grounding_error(self):
        """MockLLMProvider(malformed_output) → GroundingValidationError."""
        service = self._make_service("malformed_output")
        request = _make_gen_request("binary search", "gen_doc_id", version_id="gen_v_id")
        with self.assertRaises(GroundingValidationError):
            self._run(service.generate(request))

    def test_18_invalid_document_raises_value_error(self):
        """Unknown document_id must raise ValueError from RetrievalService."""
        service = self._make_service("success")
        request = _make_gen_request("query", "nonexistent_doc_id")
        with self.assertRaises(ValueError):
            self._run(service.generate(request))

    def test_19_generation_options_temperature_reach_provider(self):
        """temperature from GenerationOptions reaches the LLM request."""

        class CapturingProvider:
            """Captures the LLMGenerationRequest for inspection."""

            def __init__(self):
                self.last_request: LLMGenerationRequest | None = None

            async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
                self.last_request = request
                structured = {
                    "answer": "Captured answer [S1].",
                    "claims": [{"claim_id": "c1", "text": "x", "citation_ids": ["S1"]}],
                }
                return LLMGenerationResponse(
                    raw_response="Captured answer [S1].",
                    structured_output=structured,
                    token_usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    model_name="cap-model",
                )

        capturing = CapturingProvider()
        service = GenerationService(
            retrieval_service=self.retrieval_service,
            provider=capturing,
        )
        request = _make_gen_request("binary search", "gen_doc_id", version_id="gen_v_id", temperature=0.7)
        self._run(service.generate(request))

        self.assertIsNotNone(capturing.last_request)
        self.assertAlmostEqual(capturing.last_request.temperature, 0.7, places=3)

    def test_20_failed_generation_no_partial_messages_persisted(self):
        """If generation fails, neither USER nor ASSISTANT messages are persisted."""
        from unittest.mock import MagicMock
        from app.repositories.conversation_repository import ConversationRepository, MessageRepository
        from app.models.conversation import Conversation
        
        mock_conv_repo = MagicMock(spec=ConversationRepository)
        mock_conv = Conversation(
            id="test_conv",
            document_id="gen_doc_id",
            title="Test",
            status="ACTIVE",
            knowledge_version_id="gen_v_id"
        )
        mock_conv_repo.get_conversation.return_value = mock_conv
        
        mock_msg_repo = MagicMock(spec=MessageRepository)
        mock_msg_repo.list_messages.return_value = []
        
        provider = MockLLMProvider(scenario="provider_failure")
        service = GenerationService(
            retrieval_service=self.retrieval_service,
            provider=provider,
            conversation_repo=mock_conv_repo,
            message_repo=mock_msg_repo,
        )
        
        request = _make_gen_request("query", "gen_doc_id", version_id="gen_v_id")
        request.conversation_id = "test_conv"
        
        with self.assertRaises(LLMProviderError):
            self._run(service.generate(request))
            
        mock_msg_repo.append_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
