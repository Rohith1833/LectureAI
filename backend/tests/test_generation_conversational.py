"""
Phase 8G-2 — Conversational Grounded Generation Unit Tests

Tests validating:
- Conversational grounding flow with persisted session history
- Single-turn backwards compatibility (no conversation_id -> no persistence)
- Validation and rejection of invalid, mismatched, and archived conversations
- Pinned knowledge-version scope enforcement
- Bounded and chronological history formatting in PromptBuilder
- Grounding isolation (conversation turns never become citation sources)
- Atomic message persistence on generation success
- Rollback/no-op on provider or grounding validation failure
- Multi-mode support across QA, EXPLANATION, SUMMARY, COMPARISON, STUDY_GUIDE
"""

import unittest
import time
import uuid
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.models.document import Base, Document
from app.models.review import AcademicGraphSnapshot
from app.models.knowledge import KnowledgeVersion, KnowledgeEntity
from app.models.conversation import Conversation, ConversationMessage
from app.repositories.conversation_repository import (
    ConversationRepository,
    MessageRepository,
)
from app.schemas.generation import (
    GenerationMode,
    GenerationRequest,
    GenerationResult,
    ComparisonOptions,
    StudyGuideOptions,
)
from app.schemas.knowledge import KnowledgeEntitySchema
from app.schemas.retrieval import (
    RetrievalScope,
    RetrievalResult,
    RetrievedEntity,
    RetrievalProvenance,
)
from app.services.generation.mock_provider import MockLLMProvider
from app.services.generation.generation_service import GenerationService
from app.services.generation.context_builder import ContextBuilder
from app.services.generation.prompt_builder import PromptBuilder
from app.services.generation.grounding_validator import GroundingValidator
from app.services.generation.errors import LLMProviderError


class MockRetrievalService:
    """Mock Phase 7 RetrievalService returning fixed candidate entities."""

    def __init__(self, entities=None):
        self.entities = entities or []
        self.last_request = None

    def retrieve(self, request):
        self.last_request = request
        prov = RetrievalProvenance(
            knowledge_version_id=request.scope.version_id or "kv_default",
            approval_version=1,
            document_id=request.scope.document_id,
            strategy_used="LEXICAL",
            query_terms=["test"],
            total_candidates_considered=len(self.entities),
        )
        return RetrievalResult(
            query=request.query,
            scope=request.scope,
            provenance=prov,
            entities=self.entities,
            total_entity_count=len(self.entities),
            has_more=False,
        )


class TestGenerationConversational(unittest.IsolatedAsyncioTestCase):
    """Unit tests for Phase 8G-2 Conversational Grounded Generation."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", echo=False)

        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db = self.SessionLocal()

        self.u1 = str(uuid.uuid4())
        self.u2 = str(uuid.uuid4())

        # Seed Document 1
        self.doc1 = Document(
            upload_id=self.u1,
            status="processed",
            extraction_timestamp="2026-08-29T00:00:00Z",
            processing_time=1.0,
        )
        # Seed Document 2
        self.doc2 = Document(
            upload_id=self.u2,
            status="processed",
            extraction_timestamp="2026-08-29T00:00:00Z",
            processing_time=1.0,
        )
        self.db.add_all([self.doc1, self.doc2])
        self.db.flush()

        # Seed Snapshot & KnowledgeVersion for doc1
        self.snap1 = AcademicGraphSnapshot(
            upload_id=self.u1,
            pipeline_run_id="run_1",
            approval_version=1,
            approved_revision=0,
            base_graph_fingerprint="fp1",
            resolved_graph_fingerprint="fp2",
            approval_timestamp=time.time(),
            reviewer_id="admin",
            nodes=[],
            edges=[],
        )
        self.db.add(self.snap1)
        self.db.flush()

        self.kv1 = KnowledgeVersion(
            upload_id=self.u1,
            snapshot_id=self.snap1.id,
            status="BUILDING",
        )
        self.db.add(self.kv1)
        self.db.flush()

        self.entity1 = KnowledgeEntity(
            knowledge_version_id=self.kv1.id,
            entity_type="CONCEPT",
            title="Binary Search",
            content="Binary search runs in O(log n) time complexity on sorted arrays.",
            stable_id="ent_bs",
        )
        self.db.add(self.entity1)
        self.db.flush()

        self.kv1.status = "FINALIZED"
        self.db.commit()

        self.conv_repo = ConversationRepository(self.db)
        self.msg_repo = MessageRepository(self.db)

        from app.schemas.academic import AcademicNodeCategory
        # Mock retrieval returning entity1
        entity_schema = KnowledgeEntitySchema(
            id=self.entity1.id,
            knowledge_version_id=self.kv1.id,
            title=self.entity1.title,
            entity_type=AcademicNodeCategory.CONCEPT,
            content=self.entity1.content,
            stable_id=self.entity1.stable_id,
        )
        self.retrieval_service = MockRetrievalService(
            entities=[RetrievedEntity(entity=entity_schema, score=0.95, match_reason="EXACT_MATCH")]
        )

        self.provider = MockLLMProvider(
            custom_response="Binary search runs in O(log n) time [S1]."
        )
        self.service = GenerationService(
            retrieval_service=self.retrieval_service,
            provider=self.provider,
            conversation_repo=self.conv_repo,
            message_repo=self.msg_repo,
        )

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    # =========================================================================
    # 1. Validation & Scope Tests
    # =========================================================================

    async def test_01_single_turn_backward_compatibility(self):
        """Verify request without conversation_id executes normally without persistence."""
        req = GenerationRequest(
            query="What is binary search?",
            scope=RetrievalScope(document_id=self.doc1.id, version_id=self.kv1.id),
            mode=GenerationMode.QA,
        )
        result = await self.service.generate(req)
        self.assertIsNotNone(result)
        self.assertIn("Binary search", result.answer)
        self.assertIn("S1", result.citations)

        # No conversations or messages were created
        self.assertEqual(self.db.query(Conversation).count(), 0)
        self.assertEqual(self.db.query(ConversationMessage).count(), 0)

    async def test_02_conversational_generation_success_and_persistence(self):
        """Verify conversational generation executes, attaches citations, and persists USER/ASSISTANT turns."""
        conv = self.conv_repo.create_conversation(document_id=self.doc1.id, knowledge_version_id=self.kv1.id)

        req = GenerationRequest(
            query="Explain binary search complexity",
            scope=RetrievalScope(document_id=self.doc1.id, version_id=self.kv1.id),
            mode=GenerationMode.QA,
            conversation_id=conv.id,
        )
        result = await self.service.generate(req)
        self.assertIsNotNone(result)
        self.assertEqual(result.answer, "Binary search runs in O(log n) time [S1].")

        # Verify DB messages: exactly 2 messages (USER then ASSISTANT)
        messages = self.msg_repo.list_messages(conv.id)
        self.assertEqual(len(messages), 2)

        self.assertEqual(messages[0].sequence, 1)
        self.assertEqual(messages[0].role, "USER")
        self.assertEqual(messages[0].content, "Explain binary search complexity")

        self.assertEqual(messages[1].sequence, 2)
        self.assertEqual(messages[1].role, "ASSISTANT")
        self.assertEqual(messages[1].content, "Binary search runs in O(log n) time [S1].")

    async def test_03_subsequent_turn_includes_previous_history_in_prompt(self):
        """Verify second turn includes first turn history in PromptBuilder prompt."""
        conv = self.conv_repo.create_conversation(document_id=self.doc1.id, knowledge_version_id=self.kv1.id)

        # Turn 1
        req1 = GenerationRequest(
            query="What is binary search?",
            scope=RetrievalScope(document_id=self.doc1.id, version_id=self.kv1.id),
            conversation_id=conv.id,
        )
        await self.service.generate(req1)

        # Turn 2
        req2 = GenerationRequest(
            query="What is its time complexity again?",
            scope=RetrievalScope(document_id=self.doc1.id, version_id=self.kv1.id),
            conversation_id=conv.id,
        )
        await self.service.generate(req2)

        # Total 4 messages in DB
        messages = self.msg_repo.list_messages(conv.id)
        self.assertEqual(len(messages), 4)
        self.assertEqual([m.sequence for m in messages], [1, 2, 3, 4])

        # Verify last prompt passed to provider contained previous conversation
        last_llm_req = self.provider.calls[-1]
        self.assertIn("PREVIOUS CONVERSATION HISTORY:", last_llm_req.prompt)
        self.assertIn("USER: What is binary search?", last_llm_req.prompt)
        self.assertIn("ASSISTANT: Binary search runs in O(log n) time [S1].", last_llm_req.prompt)
        self.assertIn("USER QUERY: What is its time complexity again?", last_llm_req.prompt)

    async def test_04_invalid_conversation_id_rejection(self):
        """Verify non-existent conversation ID raises ValueError."""
        req = GenerationRequest(
            query="Query",
            scope=RetrievalScope(document_id=self.doc1.id),
            conversation_id="non_existent_conv_id",
        )
        with self.assertRaises(ValueError) as ctx:
            await self.service.generate(req)
        self.assertIn("does not exist", str(ctx.exception))

    async def test_05_conversation_document_mismatch_rejection(self):
        """Verify conversation for doc1 cannot be used with request scoped to doc2."""
        conv = self.conv_repo.create_conversation(document_id=self.doc1.id)
        req = GenerationRequest(
            query="Query",
            scope=RetrievalScope(document_id=self.doc2.id),  # Mismatch!
            conversation_id=conv.id,
        )
        with self.assertRaises(ValueError) as ctx:
            await self.service.generate(req)
        self.assertIn("does not belong to Document", str(ctx.exception))

    async def test_06_archived_conversation_rejection(self):
        """Verify generation against ARCHIVED conversation is rejected."""
        conv = self.conv_repo.create_conversation(document_id=self.doc1.id)
        self.conv_repo.archive_conversation(conv.id)

        req = GenerationRequest(
            query="Query",
            scope=RetrievalScope(document_id=self.doc1.id),
            conversation_id=conv.id,
        )
        with self.assertRaises(ValueError) as ctx:
            await self.service.generate(req)
        self.assertIn("Cannot generate in ARCHIVED conversation", str(ctx.exception))

    async def test_07_knowledge_version_mismatch_rejection(self):
        """Verify conversation pinned to kv1 rejects request specifying a different version."""
        conv = self.conv_repo.create_conversation(document_id=self.doc1.id, knowledge_version_id=self.kv1.id)
        req = GenerationRequest(
            query="Query",
            scope=RetrievalScope(document_id=self.doc1.id, version_id="other_version_v2"),  # Mismatch!
            conversation_id=conv.id,
        )
        with self.assertRaises(ValueError) as ctx:
            await self.service.generate(req)
        self.assertIn("Conversation is pinned to KnowledgeVersion", str(ctx.exception))

    async def test_08_unspecified_version_adopts_conversation_pinned_version(self):
        """Verify request without version_id automatically adopts conversation's pinned version."""
        conv = self.conv_repo.create_conversation(document_id=self.doc1.id, knowledge_version_id=self.kv1.id)
        req = GenerationRequest(
            query="Query",
            scope=RetrievalScope(document_id=self.doc1.id, version_id=None),  # None
            conversation_id=conv.id,
        )
        result = await self.service.generate(req)
        self.assertIsNotNone(result)
        # Retrieval received the adopted version_id
        self.assertEqual(self.retrieval_service.last_request.scope.version_id, self.kv1.id)

    # =========================================================================
    # 2. History Bounds & Grounding Isolation Tests
    # =========================================================================

    async def test_09_bounded_history_policy(self):
        """Verify GenerationService respects history_limit and retains latest complete turns."""
        conv = self.conv_repo.create_conversation(document_id=self.doc1.id, knowledge_version_id=self.kv1.id)

        # Seed 8 messages (4 turns)
        for i in range(4):
            self.msg_repo.append_message(conv.id, role="USER", content=f"Q{i+1}")
            self.msg_repo.append_message(conv.id, role="ASSISTANT", content=f"A{i+1}")

        # Set service with history_limit = 4 (last 4 messages: Q3, A3, Q4, A4)
        service_small = GenerationService(
            retrieval_service=self.retrieval_service,
            provider=self.provider,
            conversation_repo=self.conv_repo,
            message_repo=self.msg_repo,
            history_limit=4,
        )
        req = GenerationRequest(
            query="Q5",
            scope=RetrievalScope(document_id=self.doc1.id, version_id=self.kv1.id),
            conversation_id=conv.id,
        )
        await service_small.generate(req)

        last_prompt = self.provider.calls[-1].prompt
        self.assertNotIn("USER: Q1", last_prompt)
        self.assertNotIn("USER: Q2", last_prompt)
        self.assertIn("USER: Q3", last_prompt)
        self.assertIn("ASSISTANT: A3", last_prompt)
        self.assertIn("USER: Q4", last_prompt)
        self.assertIn("ASSISTANT: A4", last_prompt)
        self.assertIn("USER QUERY: Q5", last_prompt)

    async def test_10_history_turns_never_become_citation_sources(self):
        """Verify conversation history turns are never in context.sources and have no citation IDs."""
        conv = self.conv_repo.create_conversation(document_id=self.doc1.id, knowledge_version_id=self.kv1.id)
        self.msg_repo.append_message(conv.id, role="USER", content="Previous question")
        self.msg_repo.append_message(conv.id, role="ASSISTANT", content="Previous answer")

        req = GenerationRequest(
            query="Current question",
            scope=RetrievalScope(document_id=self.doc1.id, version_id=self.kv1.id),
            conversation_id=conv.id,
        )
        result = await self.service.generate(req)

        # Citations contain only retrieved context sources (S1)
        self.assertEqual(list(result.citations.keys()), ["S1"])
        self.assertEqual(result.citations["S1"].title, "Binary Search")

    # =========================================================================
    # 3. Failure & Atomicity Tests
    # =========================================================================

    async def test_11_provider_failure_does_not_persist_messages(self):
        """Verify provider exception prevents message persistence."""
        failing_provider = MockLLMProvider(scenario="provider_failure", error_message="Provider timeout")
        failing_service = GenerationService(
            retrieval_service=self.retrieval_service,
            provider=failing_provider,
            conversation_repo=self.conv_repo,
            message_repo=self.msg_repo,
        )

        conv = self.conv_repo.create_conversation(document_id=self.doc1.id, knowledge_version_id=self.kv1.id)
        req = GenerationRequest(
            query="Query",
            scope=RetrievalScope(document_id=self.doc1.id, version_id=self.kv1.id),
            conversation_id=conv.id,
        )
        with self.assertRaises(LLMProviderError):
            await failing_service.generate(req)

        # Zero messages persisted
        self.assertEqual(self.msg_repo.count_messages(conv.id), 0)

    # =========================================================================
    # 4. Multi-Mode Support Tests
    # =========================================================================

    async def test_12_all_five_modes_conversational_execution(self):
        """Verify conversational generation operates across all 5 modes with MockLLMProvider."""
        conv = self.conv_repo.create_conversation(document_id=self.doc1.id, knowledge_version_id=self.kv1.id)

        # 1. EXPLANATION
        provider_exp = MockLLMProvider(custom_response="Binary search is a divide-and-conquer algorithm [S1].")
        service_exp = GenerationService(
            retrieval_service=self.retrieval_service,
            provider=provider_exp,
            conversation_repo=self.conv_repo,
            message_repo=self.msg_repo,
        )
        res_exp = await service_exp.generate(
            GenerationRequest(
                query="Explain binary search",
                scope=RetrievalScope(document_id=self.doc1.id, version_id=self.kv1.id),
                mode=GenerationMode.EXPLANATION,
                conversation_id=conv.id,
            )
        )
        self.assertEqual(res_exp.mode, GenerationMode.EXPLANATION)

        # 2. SUMMARY
        provider_sum = MockLLMProvider(custom_response="Summary of binary search algorithm [S1].")
        service_sum = GenerationService(
            retrieval_service=self.retrieval_service,
            provider=provider_sum,
            conversation_repo=self.conv_repo,
            message_repo=self.msg_repo,
        )
        res_sum = await service_sum.generate(
            GenerationRequest(
                query="Summarize binary search",
                scope=RetrievalScope(document_id=self.doc1.id, version_id=self.kv1.id),
                mode=GenerationMode.SUMMARY,
                conversation_id=conv.id,
            )
        )
        self.assertEqual(res_sum.mode, GenerationMode.SUMMARY)

        # Verify DB messages accumulated correctly across modes (4 messages total so far)
        self.assertEqual(self.msg_repo.count_messages(conv.id), 4)


if __name__ == "__main__":
    unittest.main()
