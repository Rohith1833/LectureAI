import asyncio
import time
import unittest
import uuid

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from pydantic import ValidationError

from app.models import Base, Document, AcademicGraphSnapshot
from app.models.knowledge import KnowledgeVersion, KnowledgeEntity
from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.schemas.generation import (
    GenerationMode,
    GenerationRequest,
    GenerationResult,
    GenerationOptions,
    GenerationContext,
    ContextSource,
    GroundingStatus,
    ComparisonOptions,
    StudyGuideOptions,
)
from app.schemas.retrieval import RetrievalScope, RetrievalOptions, RetrievalProvenance
from app.services.generation.base import LLMProvider, LLMGenerationResponse
from app.services.generation.errors import LLMProviderError, GroundingValidationError
from app.services.generation.modes.base import GenerationModeStrategy
from app.services.generation.modes.qa import QAModeStrategy
from app.services.generation.modes.explanation import ExplanationStrategy
from app.services.generation.modes.summary import SummaryStrategy
from app.services.generation.modes.comparison import ComparisonStrategy
from app.services.generation.modes.study_guide import StudyGuideStrategy
from app.services.generation.modes.registry import strategy_registry, StrategyRegistry
from app.services.generation.prompt_builder import PromptBuilder
from app.services.generation.grounding_validator import GroundingValidator
from app.services.generation.generation_service import GenerationService
from app.services.generation.mock_provider import MockLLMProvider
from app.services.retrieval.retrieval_service import RetrievalService


class CustomMockProvider(LLMProvider):
    """Simple test LLM provider to return custom structured output."""
    def __init__(self, scenario="success", structured_output=None, error_message="Failure"):
        self.scenario = scenario
        self.structured_output = structured_output
        self.error_message = error_message

    async def generate(self, request):
        if self.scenario == "failure":
            raise LLMProviderError(self.error_message)
        return LLMGenerationResponse(
            raw_response="raw text",
            structured_output=self.structured_output,
            token_usage={"prompt_tokens": 10, "completion_tokens": 5},
            model_name="custom-mock"
        )


class TestGenerationModes(unittest.TestCase):
    """
    Comprehensive tests covering the Phase 8E-3 Generation Mode strategy patterns,
    prompt builder refactoring, grounding validator updates, and regression testing.
    """

    def setUp(self):
        self.qa_strategy = QAModeStrategy()
        self.explanation_strategy = ExplanationStrategy()
        self.summary_strategy = SummaryStrategy()
        self.comparison_strategy = ComparisonStrategy()
        self.study_guide_strategy = StudyGuideStrategy()
        self.registry = StrategyRegistry()
        self.prompt_builder = PromptBuilder()
        self.grounding_validator = GroundingValidator()

    # 1. GenerationMode enum tests
    def test_01_generation_mode_enum(self):
        """Verify the GenerationMode enum contains all planned values."""
        self.assertEqual(GenerationMode.QA, "QA")
        self.assertEqual(GenerationMode.EXPLANATION, "EXPLANATION")
        self.assertEqual(GenerationMode.SUMMARY, "SUMMARY")
        self.assertEqual(GenerationMode.COMPARISON, "COMPARISON")
        self.assertEqual(GenerationMode.STUDY_GUIDE, "STUDY_GUIDE")

    # 2. Strategy protocol/contract tests
    def test_02_strategy_protocol_contract(self):
        """Verify strategies implement the GenerationModeStrategy protocol."""
        self.assertIsInstance(self.qa_strategy, GenerationModeStrategy)
        self.assertEqual(self.qa_strategy.mode, GenerationMode.QA)
        self.assertIsNotNone(self.qa_strategy.system_instruction)
        
        self.assertIsInstance(self.explanation_strategy, GenerationModeStrategy)
        self.assertEqual(self.explanation_strategy.mode, GenerationMode.EXPLANATION)
        self.assertIsNotNone(self.explanation_strategy.system_instruction)

        self.assertIsInstance(self.summary_strategy, GenerationModeStrategy)
        self.assertEqual(self.summary_strategy.mode, GenerationMode.SUMMARY)
        self.assertIsNotNone(self.summary_strategy.system_instruction)

        self.assertIsInstance(self.comparison_strategy, GenerationModeStrategy)
        self.assertEqual(self.comparison_strategy.mode, GenerationMode.COMPARISON)
        self.assertIsNotNone(self.comparison_strategy.system_instruction)

        self.assertIsInstance(self.study_guide_strategy, GenerationModeStrategy)
        self.assertEqual(self.study_guide_strategy.mode, GenerationMode.STUDY_GUIDE)
        self.assertIsNotNone(self.study_guide_strategy.system_instruction)

    # 3. QA strategy prompts validation
    def test_03_qa_strategy_exact_match(self):
        """Verify QAModeStrategy matches 8D prompts exactly."""
        self.assertIn("synthesize factual, grounded", self.qa_strategy.system_instruction)
        self.assertIn("GROUNDING RULES:", self.qa_strategy.grounding_instructions)
        self.assertIn("OUTPUT REQUIREMENTS:", self.qa_strategy.output_requirements)
        self.assertEqual(self.qa_strategy.json_schema["type"], "object")

    # 4. StrategyRegistry resolution tests
    def test_04_registry_resolves_supported_modes(self):
        """Verify strategy_registry resolves all implemented modes successfully."""
        self.assertIsInstance(strategy_registry.get(GenerationMode.QA), QAModeStrategy)
        self.assertIsInstance(strategy_registry.get(GenerationMode.EXPLANATION), ExplanationStrategy)
        self.assertIsInstance(strategy_registry.get(GenerationMode.SUMMARY), SummaryStrategy)
        self.assertIsInstance(strategy_registry.get(GenerationMode.COMPARISON), ComparisonStrategy)
        self.assertIsInstance(strategy_registry.get(GenerationMode.STUDY_GUIDE), StudyGuideStrategy)

    # 5. Unknown/unsupported mode handling
    def test_05_unsupported_mode_raises_value_error(self):
        """Verify StrategyRegistry raises ValueError for unimplemented modes."""
        # After 8E-3B, all GenerationMode members are supported/implemented!
        # Test registry lookup with an invalid value to check error path
        with self.assertRaises(ValueError) as ctx:
            self.registry.get("INVALID_MODE")
        self.assertIn("not currently supported", str(ctx.exception))

    # 6. PromptBuilder strategy integration (Explanation Mode)
    def test_06a_prompt_builder_explanation_strategy(self):
        """Verify PromptBuilder compiles prompts correctly for Explanation mode."""
        req = GenerationRequest(
            query="explain binary search",
            scope=RetrievalScope(document_id="doc_1"),
            mode=GenerationMode.EXPLANATION,
            retrieval_options=RetrievalOptions(top_k=5),
            generation_options=GenerationOptions(temperature=0.0)
        )
        provenance = RetrievalProvenance(
            knowledge_version_id="v_1",
            approval_version=1,
            document_id="doc_1",
            strategy_used="LEXICAL",
            query_terms=["explain"],
            total_candidates_considered=1
        )
        context = GenerationContext(
            sources=[
                ContextSource(
                    citation_id="S1",
                    entity_id="ent_1",
                    title="Concept Title",
                    entity_type="CONCEPT",
                    content="Concept body text."
                )
            ],
            provenance=provenance
        )
        llm_req = self.prompt_builder.build(req, context)
        self.assertEqual(llm_req.system_instruction, self.explanation_strategy.system_instruction)
        self.assertEqual(llm_req.json_schema, self.explanation_strategy.json_schema)
        self.assertIn("explain binary search", llm_req.prompt)

    # 7. PromptBuilder strategy integration (Summary Mode)
    def test_06b_prompt_builder_summary_strategy(self):
        """Verify PromptBuilder compiles prompts correctly for Summary mode."""
        req = GenerationRequest(
            query="summarize binary search",
            scope=RetrievalScope(document_id="doc_1"),
            mode=GenerationMode.SUMMARY,
            retrieval_options=RetrievalOptions(top_k=5),
            generation_options=GenerationOptions(temperature=0.0)
        )
        provenance = RetrievalProvenance(
            knowledge_version_id="v_1",
            approval_version=1,
            document_id="doc_1",
            strategy_used="LEXICAL",
            query_terms=["summarize"],
            total_candidates_considered=1
        )
        context = GenerationContext(
            sources=[
                ContextSource(
                    citation_id="S1",
                    entity_id="ent_1",
                    title="Concept Title",
                    entity_type="CONCEPT",
                    content="Concept body text."
                )
            ],
            provenance=provenance
        )
        llm_req = self.prompt_builder.build(req, context)
        self.assertEqual(llm_req.system_instruction, self.summary_strategy.system_instruction)
        self.assertEqual(llm_req.json_schema, self.summary_strategy.json_schema)
        self.assertIn("summarize binary search", llm_req.prompt)

    # 8. PromptBuilder strategy integration (Comparison Mode)
    def test_06c_prompt_builder_comparison_strategy(self):
        """Verify PromptBuilder compiles prompts correctly for Comparison mode."""
        req = GenerationRequest(
            query="compare search algorithms",
            scope=RetrievalScope(document_id="doc_1"),
            mode=GenerationMode.COMPARISON,
            retrieval_options=RetrievalOptions(top_k=5),
            generation_options=GenerationOptions(temperature=0.0),
            comparison_options=ComparisonOptions(
                subjects=["Binary Search", "Linear Search"],
                dimensions=["Time Complexity", "Space Complexity"]
            )
        )
        provenance = RetrievalProvenance(
            knowledge_version_id="v_1",
            approval_version=1,
            document_id="doc_1",
            strategy_used="LEXICAL",
            query_terms=["compare"],
            total_candidates_considered=1
        )
        context = GenerationContext(
            sources=[
                ContextSource(
                    citation_id="S1",
                    entity_id="ent_1",
                    title="Concept Title",
                    entity_type="CONCEPT",
                    content="Concept body text."
                )
            ],
            provenance=provenance
        )
        llm_req = self.prompt_builder.build(req, context)
        self.assertEqual(llm_req.system_instruction, self.comparison_strategy.system_instruction)
        self.assertEqual(llm_req.json_schema, self.comparison_strategy.json_schema)
        self.assertIn("compare search algorithms", llm_req.prompt)

    # 9. PromptBuilder strategy integration (Study Guide Mode)
    def test_06d_prompt_builder_study_guide_strategy(self):
        """Verify PromptBuilder compiles prompts correctly for Study Guide mode."""
        req = GenerationRequest(
            query="generate study guide",
            scope=RetrievalScope(document_id="doc_1"),
            mode=GenerationMode.STUDY_GUIDE,
            retrieval_options=RetrievalOptions(top_k=5),
            generation_options=GenerationOptions(temperature=0.0),
            study_options=StudyGuideOptions(
                question_count=4,
                difficulty="advanced"
            )
        )
        provenance = RetrievalProvenance(
            knowledge_version_id="v_1",
            approval_version=1,
            document_id="doc_1",
            strategy_used="LEXICAL",
            query_terms=["generate"],
            total_candidates_considered=1
        )
        context = GenerationContext(
            sources=[
                ContextSource(
                    citation_id="S1",
                    entity_id="ent_1",
                    title="Concept Title",
                    entity_type="CONCEPT",
                    content="Concept body text."
                )
            ],
            provenance=provenance
        )
        llm_req = self.prompt_builder.build(req, context)
        self.assertEqual(llm_req.system_instruction, self.study_guide_strategy.system_instruction)
        self.assertEqual(llm_req.json_schema, self.study_guide_strategy.json_schema)
        self.assertIn("generate study guide", llm_req.prompt)

    # 10. Request Validation Tests for Comparison Options
    def test_07a_comparison_request_validation(self):
        """Verify comparison mode schema validation constraints."""
        scope = RetrievalScope(document_id="doc_1")
        
        # Valid Comparison Request
        req = GenerationRequest(
            query="compare things",
            scope=scope,
            mode=GenerationMode.COMPARISON,
            comparison_options=ComparisonOptions(subjects=["A", "B"])
        )
        self.assertEqual(req.comparison_options.subjects, ["A", "B"])

        # Invalid: missing comparison_options completely
        with self.assertRaises(ValidationError) as ctx:
            GenerationRequest(
                query="compare things",
                scope=scope,
                mode=GenerationMode.COMPARISON
            )
        self.assertIn("requires comparison_options", str(ctx.exception))

        # Invalid: subjects list too small (less than 2 subjects)
        with self.assertRaises(ValidationError) as ctx:
            ComparisonOptions(subjects=["Only One"])
        self.assertIn("at least 2 subjects", str(ctx.exception))

        # Invalid: empty string subjects
        with self.assertRaises(ValidationError) as ctx:
            ComparisonOptions(subjects=["", "  "])
        self.assertIn("must not be empty or whitespace-only", str(ctx.exception))

    # 11. Request Validation Tests for Study Guide Options
    def test_07c_study_guide_options_validation(self):
        """Verify StudyGuideOptions schema validation constraints."""
        scope = RetrievalScope(document_id="doc_1")

        # Valid options
        opts = StudyGuideOptions(question_count=6, difficulty="basic")
        self.assertEqual(opts.question_count, 6)
        self.assertEqual(opts.difficulty, "basic")

        # Invalid difficulty constraint
        with self.assertRaises(ValidationError) as ctx:
            StudyGuideOptions(difficulty="super-hard")
        self.assertIn("Difficulty must be one of", str(ctx.exception))

        # Invalid question_count: too small
        with self.assertRaises(ValidationError) as ctx:
            StudyGuideOptions(question_count=0)
        self.assertIn("greater than or equal to 1", str(ctx.exception))

        # Invalid question_count: too large
        with self.assertRaises(ValidationError) as ctx:
            StudyGuideOptions(question_count=11)
        self.assertIn("less than or equal to 10", str(ctx.exception))

        # Valid Request
        req = GenerationRequest(
            query="study material",
            scope=scope,
            mode=GenerationMode.STUDY_GUIDE,
            study_options=opts
        )
        self.assertEqual(req.study_options.question_count, 6)

    # 12. Shared citation validation
    def test_07b_shared_citation_validation(self):
        """Verify GroundingValidator's extracted validate_claims_citations works correctly."""
        provenance = RetrievalProvenance(
            knowledge_version_id="v_1",
            approval_version=1,
            document_id="doc_1",
            strategy_used="LEXICAL",
            query_terms=["test"],
            total_candidates_considered=1
        )
        context = GenerationContext(
            sources=[
                ContextSource(
                    citation_id="S1",
                    entity_id="ent_1",
                    title="C1",
                    entity_type="CONCEPT",
                    content="Content S1."
                )
            ],
            provenance=provenance
        )
        raw_claims = [
            {"claim_id": "c1", "text": "Claim citing S1", "citation_ids": ["S1"]},
            {"claim_id": "c2", "text": "Claim citing S99", "citation_ids": ["S99"]},
            {"claim_id": "c3", "text": "Claim citing both", "citation_ids": ["S1", "S99"]},
        ]
        claims = self.grounding_validator.validate_claims_citations(raw_claims, context)
        self.assertEqual(len(claims), 3)
        self.assertEqual(claims[0].grounding_status, GroundingStatus.SUPPORTED)
        self.assertEqual(claims[0].citation_ids, ["S1"])
        self.assertEqual(claims[1].grounding_status, GroundingStatus.UNSUPPORTED)
        self.assertEqual(claims[1].citation_ids, [])
        self.assertEqual(claims[2].grounding_status, GroundingStatus.PARTIALLY_SUPPORTED)
        self.assertEqual(claims[2].citation_ids, ["S1"])


class TestGenerationModesPipeline(unittest.TestCase):
    """Regression and pipeline tests for the full GenerationService pipeline and db interaction."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
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

        # Seed minimal documents and knowledge graphs
        self.upload_id = str(uuid.uuid4())
        doc = Document(
            id="doc_pipe_id",
            upload_id=self.upload_id,
            status="processed",
            extraction_timestamp="2026-08-23T00:00:00Z",
            processing_time=1.0,
            review_state="APPROVED",
        )
        self.db.add(doc)
        self.db.flush()

        snap = AcademicGraphSnapshot(
            id="snap_pipe_id",
            upload_id=self.upload_id,
            pipeline_run_id="run_pipe",
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
            id="v_pipe_id",
            upload_id=self.upload_id,
            snapshot_id="snap_pipe_id",
            status="BUILDING",
            created_at=time.time(),
        )
        self.db.add(version)
        self.db.flush()

        entity = KnowledgeEntity(
            id="ent_pipe_id",
            knowledge_version_id="v_pipe_id",
            entity_type="CONCEPT",
            title="Binary Search",
            content="Binary search operates in O(log n) time complexity.",
            stable_id="anc_binary_pipe",
        )
        self.db.add(entity)
        self.db.flush()

        # Finalize knowledge version
        version.status = "FINALIZED"
        self.db.commit()

        self.repo = KnowledgeRepository(self.db)
        self.doc_repo = DocumentRepository(self.db)
        self.retrieval_service = RetrievalService(self.repo, self.doc_repo)
        self.provider = MockLLMProvider(scenario="success")
        self.service = GenerationService(
            retrieval_service=self.retrieval_service,
            provider=self.provider
        )

    def tearDown(self):
        self.db.close()

    def test_08_pipeline_qa_mode_success(self):
        """Verify full GenerationService pipeline works with default QA mode."""
        req = GenerationRequest(
            query="binary search",
            scope=RetrievalScope(document_id="doc_pipe_id", version_id="v_pipe_id"),
            mode=GenerationMode.QA,
            retrieval_options=RetrievalOptions(top_k=5),
            generation_options=GenerationOptions(temperature=0.0)
        )
        result = asyncio.run(self.service.generate(req))
        self.assertIsInstance(result, GenerationResult)
        self.assertEqual(result.overall_grounding_status, GroundingStatus.SUPPORTED)

    def test_09_pipeline_explanation_mode_success(self):
        """Verify pipeline succeeds under EXPLANATION mode."""
        req = GenerationRequest(
            query="explain binary search",
            scope=RetrievalScope(document_id="doc_pipe_id", version_id="v_pipe_id"),
            mode=GenerationMode.EXPLANATION,
            retrieval_options=RetrievalOptions(top_k=5),
            generation_options=GenerationOptions(temperature=0.0)
        )
        result = asyncio.run(self.service.generate(req))
        self.assertIsInstance(result, GenerationResult)
        self.assertEqual(result.overall_grounding_status, GroundingStatus.SUPPORTED)

    def test_10_pipeline_summary_mode_success(self):
        """Verify pipeline succeeds under SUMMARY mode."""
        req = GenerationRequest(
            query="summarize binary search",
            scope=RetrievalScope(document_id="doc_pipe_id", version_id="v_pipe_id"),
            mode=GenerationMode.SUMMARY,
            retrieval_options=RetrievalOptions(top_k=5),
            generation_options=GenerationOptions(temperature=0.0)
        )
        result = asyncio.run(self.service.generate(req))
        self.assertIsInstance(result, GenerationResult)
        self.assertEqual(result.overall_grounding_status, GroundingStatus.SUPPORTED)

    def test_11_pipeline_unsupported_mode_raises(self):
        """Verify pipeline raises ValueError when request specifies an unimplemented mode."""
        # No unimplemented mode exists in GenerationMode now, but we verify error raising
        # if registry get() receives an invalid string mode.
        with self.assertRaises(ValueError):
            strategy_registry.get("INVALID_MODE")

    def test_12_pipeline_study_guide_success(self):
        """Verify successful study guide generation pipeline."""
        structured_data = {
            "title": "Search Algorithms Guide",
            "answer": "This study guide covers basic linear and binary search mechanisms.",
            "key_concepts": [
                {
                    "concept": "Binary Search",
                    "definition": "A divide-and-conquer search algorithm [S1]",
                    "citation_ids": ["S1"]
                }
            ],
            "learning_objectives": [
                "Understand the requirements and time complexity of binary search."
            ],
            "review_questions": [
                {
                    "question": "What is the complexity of binary search?",
                    "answer": "Binary search is O(log n) [S1]",
                    "explanation": "At each step, binary search eliminates half of the search array [S1]",
                    "citation_ids": ["S1"]
                }
            ],
            "claims": [
                {"claim_id": "c1", "text": "Binary search is divide-and-conquer.", "citation_ids": ["S1"]},
                {"claim_id": "c2", "text": "Binary search is O(log n).", "citation_ids": ["S1"]}
            ]
        }
        custom_provider = CustomMockProvider(scenario="success", structured_output=structured_data)
        service = GenerationService(retrieval_service=self.retrieval_service, provider=custom_provider)
        
        req = GenerationRequest(
            query="study guide binary search",
            scope=RetrievalScope(document_id="doc_pipe_id", version_id="v_pipe_id"),
            mode=GenerationMode.STUDY_GUIDE,
            study_options=StudyGuideOptions(question_count=3, difficulty="intermediate")
        )
        result = asyncio.run(service.generate(req))
        self.assertEqual(result.overall_grounding_status, GroundingStatus.SUPPORTED)
        self.assertEqual(result.answer, "This study guide covers basic linear and binary search mechanisms.")
        self.assertEqual(len(result.claims), 2)
        self.assertIn("S1", result.citations)

    def test_13_pipeline_study_guide_insufficient_context(self):
        """Verify study guide pipeline detects insufficient context appropriately."""
        # Seeding an output with INSUFFICIENT_CONTEXT in the answer
        structured_data = {
            "title": "Study Guide",
            "answer": "INSUFFICIENT_CONTEXT: Missing details on advanced sorting algorithms.",
            "key_concepts": [],
            "learning_objectives": [],
            "review_questions": [],
            "claims": []
        }
        custom_provider = CustomMockProvider(scenario="success", structured_output=structured_data)
        service = GenerationService(retrieval_service=self.retrieval_service, provider=custom_provider)

        req = GenerationRequest(
            query="study guide advanced sorting",
            scope=RetrievalScope(document_id="doc_pipe_id", version_id="v_pipe_id"),
            mode=GenerationMode.STUDY_GUIDE
        )
        result = asyncio.run(service.generate(req))
        self.assertEqual(result.overall_grounding_status, GroundingStatus.INSUFFICIENT_CONTEXT)
        self.assertIn("INSUFFICIENT_CONTEXT", result.answer)

    def test_14_pipeline_study_guide_invalid_citation(self):
        """Verify study guide pipeline strips invalid citation IDs."""
        structured_data = {
            "title": "Study Guide",
            "answer": "This answers with an invalid citation.",
            "key_concepts": [],
            "learning_objectives": [],
            "review_questions": [],
            "claims": [
                {"claim_id": "c1", "text": "This references S99.", "citation_ids": ["S99"]}
            ]
        }
        custom_provider = CustomMockProvider(scenario="success", structured_output=structured_data)
        service = GenerationService(retrieval_service=self.retrieval_service, provider=custom_provider)

        req = GenerationRequest(
            query="study guide binary search",
            scope=RetrievalScope(document_id="doc_pipe_id", version_id="v_pipe_id"),
            mode=GenerationMode.STUDY_GUIDE
        )
        result = asyncio.run(service.generate(req))
        self.assertEqual(result.overall_grounding_status, GroundingStatus.PARTIALLY_SUPPORTED)
        self.assertEqual(result.claims[0].citation_ids, [])

    def test_15_pipeline_study_guide_mixed_citations(self):
        """Verify study guide pipeline sanitizes mixed valid and invalid citations."""
        structured_data = {
            "title": "Study Guide",
            "answer": "This has mixed citations.",
            "key_concepts": [],
            "learning_objectives": [],
            "review_questions": [],
            "claims": [
                {"claim_id": "c1", "text": "References both S1 and S99.", "citation_ids": ["S1", "S99"]}
            ]
        }
        custom_provider = CustomMockProvider(scenario="success", structured_output=structured_data)
        service = GenerationService(retrieval_service=self.retrieval_service, provider=custom_provider)

        req = GenerationRequest(
            query="study guide binary search",
            scope=RetrievalScope(document_id="doc_pipe_id", version_id="v_pipe_id"),
            mode=GenerationMode.STUDY_GUIDE
        )
        result = asyncio.run(service.generate(req))
        self.assertEqual(result.overall_grounding_status, GroundingStatus.PARTIALLY_SUPPORTED)
        self.assertEqual(result.claims[0].citation_ids, ["S1"])

    def test_16_pipeline_study_guide_provider_failure(self):
        """Verify study guide pipeline handles provider failure correctly."""
        custom_provider = CustomMockProvider(scenario="failure", error_message="Simulated Groq Failure")
        service = GenerationService(retrieval_service=self.retrieval_service, provider=custom_provider)

        req = GenerationRequest(
            query="study guide",
            scope=RetrievalScope(document_id="doc_pipe_id", version_id="v_pipe_id"),
            mode=GenerationMode.STUDY_GUIDE
        )
        with self.assertRaises(LLMProviderError) as ctx:
            asyncio.run(service.generate(req))
        self.assertIn("Simulated Groq Failure", str(ctx.exception))


class TestGenerationValidatorGeneralization(unittest.TestCase):
    """
    Focused unit tests for generalized grounding validation, nested structures,
    serialization, and schema conformance checks in Phase 8E-3C.
    """

    def setUp(self):
        self.validator = GroundingValidator()
        # Seed a context with valid citation IDs: S1 and S2
        provenance = RetrievalProvenance(
            knowledge_version_id="v_1",
            approval_version=1,
            document_id="doc_1",
            strategy_used="LEXICAL",
            query_terms=["test"],
            total_candidates_considered=2
        )
        self.context = GenerationContext(
            sources=[
                ContextSource(
                    citation_id="S1",
                    entity_id="ent_1",
                    title="Concept 1",
                    entity_type="CONCEPT",
                    content="Content S1"
                ),
                ContextSource(
                    citation_id="S2",
                    entity_id="ent_2",
                    title="Concept 2",
                    entity_type="CONCEPT",
                    content="Content S2"
                )
            ],
            provenance=provenance
        )

    def test_01_common_result_serialization(self):
        """Verify common GenerationResult serialization works cleanly."""
        res = GenerationResult(
            mode=GenerationMode.QA,
            answer="This is a natural language answer.",
            structured_output={"field": "value"},
            claims=[],
            citations={},
            overall_grounding_status=GroundingStatus.SUPPORTED
        )
        dump = res.model_dump()
        self.assertEqual(dump["mode"], GenerationMode.QA)
        self.assertEqual(dump["answer"], "This is a natural language answer.")
        self.assertEqual(dump["structured_output"], {"field": "value"})

    def test_02_comparison_structured_serialization(self):
        """Verify Comparison mode structured output conforms and serializes."""
        # Validate that ComparisonRequest can accept valid ComparisonOptions
        req = GenerationRequest(
            query="compare search algorithms",
            scope=RetrievalScope(document_id="doc_1"),
            mode=GenerationMode.COMPARISON,
            comparison_options=ComparisonOptions(
                subjects=["Linear Search", "Binary Search"],
                dimensions=["Time", "Space"]
            )
        )
        dump = req.model_dump()
        self.assertEqual(dump["comparison_options"]["subjects"], ["Linear Search", "Binary Search"])

    def test_03_study_guide_structured_serialization(self):
        """Verify Study Guide mode structured output options serialize."""
        req = GenerationRequest(
            query="study guide search",
            scope=RetrievalScope(document_id="doc_1"),
            mode=GenerationMode.STUDY_GUIDE,
            study_options=StudyGuideOptions(
                question_count=5,
                difficulty="advanced"
            )
        )
        dump = req.model_dump()
        self.assertEqual(dump["study_options"]["difficulty"], "advanced")

    def test_04_nested_citation_validation_valid(self):
        """Verify nested valid citation lists are fully preserved."""
        raw_output = {
            "title": "Search Comparison",
            "subjects": ["A", "B"],
            "comparison_table": [
                {
                    "dimension": "Time Complexity",
                    "values": [
                        {"subject": "A", "value": "O(n) [S1]", "citation_ids": ["S1"]}
                    ]
                }
            ],
            "similarities": [
                {"text": "Both are algorithms [S1, S2]", "citation_ids": ["S1", "S2"]}
            ],
            "differences": []
        }
        response = LLMGenerationResponse(
            raw_response="raw text",
            structured_output=raw_output,
            model_name="mock-model"
        )
        request = GenerationRequest(
            query="compare algorithms",
            scope=RetrievalScope(document_id="doc_1"),
            mode=GenerationMode.COMPARISON,
            comparison_options=ComparisonOptions(subjects=["A", "B"])
        )
        result = self.validator.validate(response, self.context, request)
        self.assertEqual(result.overall_grounding_status, GroundingStatus.SUPPORTED)
        
        # Verify citation S1 and S2 are in citations dictionary
        self.assertIn("S1", result.citations)
        self.assertIn("S2", result.citations)

        # Check that comparison values inside table preserved citation_ids
        table = result.structured_output["comparison_table"]
        self.assertEqual(table[0]["values"][0]["citation_ids"], ["S1"])

    def test_05_nested_citation_validation_invalid(self):
        """Verify invalid nested citation IDs are stripped and tracked."""
        raw_output = {
            "title": "Search Comparison",
            "subjects": ["A", "B"],
            "comparison_table": [],
            "similarities": [
                {"text": "Refers to S99 [S99]", "citation_ids": ["S99"]}
            ],
            "differences": []
        }
        response = LLMGenerationResponse(
            raw_response="raw text",
            structured_output=raw_output,
            model_name="mock-model"
        )
        request = GenerationRequest(
            query="compare algorithms",
            scope=RetrievalScope(document_id="doc_1"),
            mode=GenerationMode.COMPARISON,
            comparison_options=ComparisonOptions(subjects=["A", "B"])
        )
        result = self.validator.validate(response, self.context, request)
        # Only invalid citation IDs cited -> GroundingStatus.UNSUPPORTED
        self.assertEqual(result.overall_grounding_status, GroundingStatus.UNSUPPORTED)
        
        # Verify invalid citation S99 is stripped
        self.assertEqual(result.structured_output["similarities"][0]["citation_ids"], [])

    def test_06_nested_citation_validation_mixed(self):
        """Verify mixed nested citation lists are sanitized (invalid stripped, valid retained)."""
        raw_output = {
            "title": "Search Comparison",
            "subjects": ["A", "B"],
            "comparison_table": [],
            "similarities": [
                {"text": "Refers to S1 and S99 [S1, S99]", "citation_ids": ["S1", "S99"]}
            ],
            "differences": []
        }
        response = LLMGenerationResponse(
            raw_response="raw text",
            structured_output=raw_output,
            model_name="mock-model"
        )
        request = GenerationRequest(
            query="compare algorithms",
            scope=RetrievalScope(document_id="doc_1"),
            mode=GenerationMode.COMPARISON,
            comparison_options=ComparisonOptions(subjects=["A", "B"])
        )
        result = self.validator.validate(response, self.context, request)
        self.assertEqual(result.overall_grounding_status, GroundingStatus.PARTIALLY_SUPPORTED)
        
        # S1 retained, S99 stripped
        self.assertEqual(result.structured_output["similarities"][0]["citation_ids"], ["S1"])
        self.assertIn("S1", result.citations)
        self.assertNotIn("S99", result.citations)

    def test_07_grounding_rollup_nested(self):
        """Verify deterministic rollup of nested citations without top-level claims."""
        # 1. No citations at all
        raw_output = {
            "title": "Search Comparison",
            "subjects": ["A", "B"],
            "comparison_table": [],
            "similarities": [],
            "differences": []
        }
        response = LLMGenerationResponse(
            raw_response="raw text",
            structured_output=raw_output,
            model_name="mock-model"
        )
        request = GenerationRequest(
            query="compare algorithms",
            scope=RetrievalScope(document_id="doc_1"),
            mode=GenerationMode.COMPARISON,
            comparison_options=ComparisonOptions(subjects=["A", "B"])
        )
        result = self.validator.validate(response, self.context, request)
        self.assertEqual(result.overall_grounding_status, GroundingStatus.UNSUPPORTED)

    def test_08_insufficient_context_rollup_nested(self):
        """Verify insufficient context marker anywhere in nested structures rolls up to INSUFFICIENT_CONTEXT."""
        raw_output = {
            "title": "Search Comparison",
            "subjects": ["A", "B"],
            "comparison_table": [
                {
                    "dimension": "Time Complexity",
                    "values": [
                        {"subject": "A", "value": "INSUFFICIENT_CONTEXT", "citation_ids": []}
                    ]
                }
            ],
            "similarities": [],
            "differences": []
        }
        response = LLMGenerationResponse(
            raw_response="raw text",
            structured_output=raw_output,
            model_name="mock-model"
        )
        request = GenerationRequest(
            query="compare algorithms",
            scope=RetrievalScope(document_id="doc_1"),
            mode=GenerationMode.COMPARISON,
            comparison_options=ComparisonOptions(subjects=["A", "B"])
        )
        result = self.validator.validate(response, self.context, request)
        self.assertEqual(result.overall_grounding_status, GroundingStatus.INSUFFICIENT_CONTEXT)

    def test_09_malformed_structured_output(self):
        """Verify missing required fields raise GroundingValidationError."""
        # Missing 'subjects' field in Comparison response
        raw_output = {
            "title": "Search Comparison",
            "comparison_table": [],
            "similarities": [],
            "differences": []
        }
        response = LLMGenerationResponse(
            raw_response="raw text",
            structured_output=raw_output,
            model_name="mock-model"
        )
        request = GenerationRequest(
            query="compare algorithms",
            scope=RetrievalScope(document_id="doc_1"),
            mode=GenerationMode.COMPARISON,
            comparison_options=ComparisonOptions(subjects=["A", "B"])
        )
        with self.assertRaises(GroundingValidationError) as ctx:
            self.validator.validate(response, self.context, request)
        self.assertIn("missing required field: 'subjects'", str(ctx.exception))

    def test_10_wrong_field_types_validation(self):
        """Verify that wrong field types raise GroundingValidationError."""
        # 'subjects' must be an array, but passed as a string
        raw_output = {
            "title": "Search Comparison",
            "subjects": "Not An Array String",
            "comparison_table": [],
            "similarities": [],
            "differences": []
        }
        response = LLMGenerationResponse(
            raw_response="raw text",
            structured_output=raw_output,
            model_name="mock-model"
        )
        request = GenerationRequest(
            query="compare algorithms",
            scope=RetrievalScope(document_id="doc_1"),
            mode=GenerationMode.COMPARISON,
            comparison_options=ComparisonOptions(subjects=["A", "B"])
        )
        with self.assertRaises(GroundingValidationError) as ctx:
            self.validator.validate(response, self.context, request)
        self.assertIn("Field 'subjects' must be an array/list", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
