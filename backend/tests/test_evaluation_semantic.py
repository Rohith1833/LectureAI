"""
Phase 8F-3 — Semantic Grounding & Relevance Evaluator Unit Tests

Tests validating:
- FaithfulnessEvaluator support heuristic against cited context sources
- Technical token preservation (e.g. O(log n), numbers)
- Uncited and invalid citation claim handling
- RelevanceEvaluator query keyword recall across text and structured modes
- Immutability and determinism across repeated evaluation runs
- Complete 5-evaluator EvaluationEngine orchestration
"""

import unittest
import copy
from app.schemas.generation import (
    GenerationMode,
    GenerationRequest,
    GenerationResult,
    GenerationClaim,
    GroundingStatus,
    ContextSource,
    ComparisonOptions,
    StudyGuideOptions,
)
from app.schemas.retrieval import RetrievalScope
from app.schemas.evaluation import EvaluationRequest, EvaluationVerdict
from app.services.evaluation.evaluators.structural import StructuralEvaluator
from app.services.evaluation.evaluators.citation import CitationEvaluator
from app.services.evaluation.evaluators.abstention import AbstentionEvaluator
from app.services.evaluation.evaluators.faithfulness import FaithfulnessEvaluator
from app.services.evaluation.evaluators.relevance import RelevanceEvaluator
from app.services.evaluation import EvaluationEngine, create_default_evaluation_engine


def make_context_source(citation_id: str, title: str, content: str, passage_text: str = "") -> ContextSource:
    """Helper creating a populated ContextSource object."""
    passage = None
    if passage_text:
        passage = {"page_number": 1, "text": passage_text, "score": 1.0}
    return ContextSource(
        citation_id=citation_id,
        entity_id=f"ent_{citation_id}",
        title=title,
        entity_type="CONCEPT",
        content=content,
        passage=passage,
        provenance="Page 1",
    )


class TestSemanticEvaluators(unittest.IsolatedAsyncioTestCase):
    """Unit tests for Phase 8F-3 semantic evaluators."""

    def setUp(self):
        self.scope = RetrievalScope(document_id="doc_semantic", version_id="v_1")

    # =========================================================================
    # 1. FaithfulnessEvaluator Tests
    # =========================================================================

    async def test_01_faithfulness_clearly_supported_claim(self):
        """Verify FaithfulnessEvaluator scores 1.0 when claim terms match cited source."""
        evaluator = FaithfulnessEvaluator()
        source_content = "Binary search is a search algorithm that finds the position of a target value within a sorted array."
        source = make_context_source("S1", "Binary Search", source_content)

        claim = GenerationClaim(
            claim_id="c1",
            text="Binary search finds target values within a sorted array.",
            citation_ids=["S1"],
            grounding_status=GroundingStatus.SUPPORTED,
        )
        req = EvaluationRequest(
            generation_request=GenerationRequest(query="What is binary search?", scope=self.scope, mode=GenerationMode.QA),
            generation_result=GenerationResult(
                mode=GenerationMode.QA,
                answer="Binary search finds target values in sorted arrays [S1].",
                claims=[claim],
                citations={"S1": source},
                overall_grounding_status=GroundingStatus.SUPPORTED,
                model_metadata=None,
            ),
            context_sources={"S1": source},
        )
        scores = await evaluator.evaluate(req)
        self.assertEqual(len(scores), 1)
        self.assertEqual(scores[0].name, "claim_faithfulness_score")
        self.assertGreaterEqual(scores[0].score, 0.85)
        self.assertTrue(scores[0].passed)
        self.assertEqual(scores[0].metadata["supported_claims"], 1)

    async def test_02_faithfulness_unrelated_source(self):
        """Verify FaithfulnessEvaluator detects unsupported claim when source discusses unrelated topic."""
        evaluator = FaithfulnessEvaluator()
        source_content = "Photosynthesis is the process used by plants to convert light energy into chemical energy."
        source = make_context_source("S1", "Photosynthesis", source_content)

        claim = GenerationClaim(
            claim_id="c1",
            text="Binary search has logarithmic time complexity.",
            citation_ids=["S1"],
            grounding_status=GroundingStatus.SUPPORTED,
        )
        req = EvaluationRequest(
            generation_request=GenerationRequest(query="What is binary search?", scope=self.scope, mode=GenerationMode.QA),
            generation_result=GenerationResult(
                mode=GenerationMode.QA,
                answer="Binary search is fast [S1].",
                claims=[claim],
                citations={"S1": source},
                overall_grounding_status=GroundingStatus.SUPPORTED,
                model_metadata=None,
            ),
            context_sources={"S1": source},
        )
        scores = await evaluator.evaluate(req)
        self.assertLess(scores[0].score, 0.35)
        self.assertFalse(scores[0].passed)
        self.assertEqual(scores[0].metadata["unsupported_claims"], 1)

    async def test_03_faithfulness_multiple_citations_best_match(self):
        """Verify multi-citation claims take maximum support across valid cited sources."""
        evaluator = FaithfulnessEvaluator()
        src1 = make_context_source("S1", "Unrelated", "Topic about network protocols and TCP handshake.")
        src2 = make_context_source("S2", "Sorting", "Quicksort partitions the array around a pivot element.")

        claim = GenerationClaim(
            claim_id="c1",
            text="Quicksort selects a pivot element to partition the array.",
            citation_ids=["S1", "S2"],
            grounding_status=GroundingStatus.SUPPORTED,
        )
        req = EvaluationRequest(
            generation_request=GenerationRequest(query="How does quicksort work?", scope=self.scope, mode=GenerationMode.QA),
            generation_result=GenerationResult(
                mode=GenerationMode.QA,
                answer="Quicksort partitions arrays [S1][S2].",
                claims=[claim],
                citations={"S1": src1, "S2": src2},
                overall_grounding_status=GroundingStatus.SUPPORTED,
                model_metadata=None,
            ),
            context_sources={"S1": src1, "S2": src2},
        )
        scores = await evaluator.evaluate(req)
        self.assertGreaterEqual(scores[0].score, 0.80)
        self.assertTrue(scores[0].passed)

    async def test_04_faithfulness_uncited_and_invalid_citations(self):
        """Verify uncited claims and claims citing non-existent IDs receive 0.0."""
        evaluator = FaithfulnessEvaluator()
        src1 = make_context_source("S1", "Binary Search", "Operates in O(log n) time.")

        claim_uncited = GenerationClaim(claim_id="c1", text="Uncited statement.", citation_ids=[], grounding_status=GroundingStatus.UNSUPPORTED)
        claim_invalid = GenerationClaim(claim_id="c2", text="Invalid source statement.", citation_ids=["S99"], grounding_status=GroundingStatus.UNSUPPORTED)

        req = EvaluationRequest(
            generation_request=GenerationRequest(query="Question", scope=self.scope, mode=GenerationMode.QA),
            generation_result=GenerationResult(
                mode=GenerationMode.QA,
                answer="Response text",
                claims=[claim_uncited, claim_invalid],
                citations={"S1": src1},
                overall_grounding_status=GroundingStatus.UNSUPPORTED,
                model_metadata=None,
            ),
            context_sources={"S1": src1},  # S99 does not exist
        )
        scores = await evaluator.evaluate(req)
        self.assertEqual(scores[0].score, 0.0)
        self.assertFalse(scores[0].passed)
        self.assertEqual(scores[0].metadata["uncited_claims"], 1)
        self.assertEqual(scores[0].metadata["invalid_citation_claims"], 1)

    async def test_05_faithfulness_preserves_technical_big_o_tokens(self):
        """Verify technical terms like O(log n) and O(n^2) are preserved during faithfulness scoring."""
        evaluator = FaithfulnessEvaluator()
        src = make_context_source("S1", "Complexity", "Binary search runs in O(log n) worst-case time complexity.")

        claim = GenerationClaim(
            claim_id="c1",
            text="The algorithm has O(log n) time complexity.",
            citation_ids=["S1"],
            grounding_status=GroundingStatus.SUPPORTED,
        )
        req = EvaluationRequest(
            generation_request=GenerationRequest(query="Complexity?", scope=self.scope, mode=GenerationMode.QA),
            generation_result=GenerationResult(
                mode=GenerationMode.QA,
                answer="Time complexity is O(log n) [S1].",
                claims=[claim],
                citations={"S1": src},
                overall_grounding_status=GroundingStatus.SUPPORTED,
                model_metadata=None,
            ),
            context_sources={"S1": src},
        )
        scores = await evaluator.evaluate(req)
        self.assertGreaterEqual(scores[0].score, 0.80)
        self.assertTrue(scores[0].passed)

    # =========================================================================
    # 2. RelevanceEvaluator Tests
    # =========================================================================

    async def test_06_relevance_strongly_relevant_answer(self):
        """Verify RelevanceEvaluator scores 1.0 when query keywords are matched in answer."""
        evaluator = RelevanceEvaluator()
        req = EvaluationRequest(
            generation_request=GenerationRequest(
                query="How does Dijkstra algorithm compute shortest paths in weighted graphs?",
                scope=self.scope,
                mode=GenerationMode.QA,
            ),
            generation_result=GenerationResult(
                mode=GenerationMode.QA,
                answer="Dijkstra algorithm computes the shortest paths from a source node to all other nodes in weighted graphs.",
                claims=[],
                citations={},
                overall_grounding_status=GroundingStatus.SUPPORTED,
                model_metadata=None,
            ),
        )
        scores = await evaluator.evaluate(req)
        self.assertEqual(len(scores), 1)
        self.assertEqual(scores[0].name, "answer_relevance_score")
        self.assertGreaterEqual(scores[0].score, 0.80)
        self.assertTrue(scores[0].passed)

    async def test_07_relevance_irrelevant_answer(self):
        """Verify RelevanceEvaluator penalizes answers discussing unrelated topics."""
        evaluator = RelevanceEvaluator()
        req = EvaluationRequest(
            generation_request=GenerationRequest(
                query="How does Dijkstra algorithm compute shortest paths?",
                scope=self.scope,
                mode=GenerationMode.QA,
            ),
            generation_result=GenerationResult(
                mode=GenerationMode.QA,
                answer="The Roman Empire reached its greatest extent under Emperor Trajan in 117 AD.",
                claims=[],
                citations={},
                overall_grounding_status=GroundingStatus.UNSUPPORTED,
                model_metadata=None,
            ),
        )
        scores = await evaluator.evaluate(req)
        self.assertEqual(scores[0].score, 0.0)
        self.assertFalse(scores[0].passed)

    async def test_08_relevance_short_query_keyword_match(self):
        """Verify RelevanceEvaluator accurately evaluates short 1-2 term queries."""
        evaluator = RelevanceEvaluator()
        req = EvaluationRequest(
            generation_request=GenerationRequest(query="Quicksort?", scope=self.scope, mode=GenerationMode.QA),
            generation_result=GenerationResult(
                mode=GenerationMode.QA,
                answer="Quicksort is an efficient in-place divide-and-conquer sorting algorithm.",
                claims=[],
                citations={},
                overall_grounding_status=GroundingStatus.SUPPORTED,
                model_metadata=None,
            ),
        )
        scores = await evaluator.evaluate(req)
        self.assertEqual(scores[0].score, 1.0)
        self.assertTrue(scores[0].passed)

    async def test_09_relevance_comparison_mode_subjects_matching(self):
        """Verify Comparison mode relevance evaluates coverage of explicitly requested subjects."""
        evaluator = RelevanceEvaluator()
        comparison_dict = {
            "title": "Merge Sort vs Quick Sort Comparison",
            "subjects": ["Merge Sort", "Quick Sort"],
            "comparison_table": [
                {
                    "dimension": "Time Complexity",
                    "values": [
                        {"subject": "Merge Sort", "value": "O(n log n)", "citation_ids": []},
                        {"subject": "Quick Sort", "value": "O(n log n) average", "citation_ids": []},
                    ],
                }
            ],
            "similarities": [],
            "differences": [],
        }
        req = EvaluationRequest(
            generation_request=GenerationRequest(
                query="Compare sorting algorithms",
                scope=self.scope,
                mode=GenerationMode.COMPARISON,
                comparison_options=ComparisonOptions(subjects=["Merge Sort", "Quick Sort"]),
            ),
            generation_result=GenerationResult(
                mode=GenerationMode.COMPARISON,
                answer="Comparison Overview",
                claims=[],
                citations={},
                overall_grounding_status=GroundingStatus.SUPPORTED,
                model_metadata=None,
                structured_output=comparison_dict,
            ),
        )
        scores = await evaluator.evaluate(req)
        self.assertGreaterEqual(scores[0].score, 0.80)
        self.assertTrue(scores[0].passed)

    async def test_10_relevance_insufficient_context_abstention_scored_perfect(self):
        """Verify model receives 1.0 relevance when properly abstaining on insufficient context."""
        evaluator = RelevanceEvaluator()
        req = EvaluationRequest(
            generation_request=GenerationRequest(query="Unanswerable question", scope=self.scope, mode=GenerationMode.QA),
            generation_result=GenerationResult(
                mode=GenerationMode.QA,
                answer="INSUFFICIENT_CONTEXT",
                claims=[],
                citations={},
                overall_grounding_status=GroundingStatus.INSUFFICIENT_CONTEXT,
                model_metadata=None,
            ),
        )
        scores = await evaluator.evaluate(req)
        self.assertEqual(scores[0].score, 1.0)
        self.assertTrue(scores[0].passed)

    # =========================================================================
    # 3. Engine Integration & Determinism Tests
    # =========================================================================

    async def test_11_full_default_engine_5_evaluators(self):
        """Verify EvaluationEngine orchestrates all 5 core evaluators."""
        engine = EvaluationEngine([
            StructuralEvaluator(),
            CitationEvaluator(),
            AbstentionEvaluator(),
            FaithfulnessEvaluator(),
            RelevanceEvaluator(),
        ])
        self.assertEqual(len(engine.evaluators), 5)

        src = make_context_source("S1", "Binary Search", "Binary search is O(log n) time complexity in sorted arrays.")
        claim = GenerationClaim(
            claim_id="c1",
            text="Binary search operates in O(log n) time complexity.",
            citation_ids=["S1"],
            grounding_status=GroundingStatus.SUPPORTED,
        )
        req = EvaluationRequest(
            generation_request=GenerationRequest(query="Explain binary search complexity", scope=self.scope, mode=GenerationMode.QA),
            generation_result=GenerationResult(
                mode=GenerationMode.QA,
                answer="Binary search runs in O(log n) time complexity [S1].",
                claims=[claim],
                citations={"S1": src},
                overall_grounding_status=GroundingStatus.SUPPORTED,
                model_metadata={"model_name": "test-model"},
            ),
            context_sources={"S1": src},
        )

        result = await engine.evaluate(req)
        self.assertTrue(result.overall_passed)
        self.assertEqual(result.verdict, EvaluationVerdict.PASS)
        self.assertGreaterEqual(result.overall_score, 0.90)

        metric_names = {m.name for m in result.metrics}
        self.assertIn("schema_compliance_score", metric_names)
        self.assertIn("citation_validity_rate", metric_names)
        self.assertIn("claim_citation_coverage", metric_names)
        self.assertIn("empty_abstention_accuracy", metric_names)
        self.assertIn("claim_faithfulness_score", metric_names)
        self.assertIn("answer_relevance_score", metric_names)

    async def test_12_determinism_and_immutability(self):
        """Verify identical inputs yield exact same evaluation metrics and leave input untouched."""
        engine = create_default_evaluation_engine()
        src = make_context_source("S1", "Hashing", "Hash tables provide average O(1) lookups.")
        claim = GenerationClaim(claim_id="c1", text="Hash tables provide O(1) average lookup time.", citation_ids=["S1"], grounding_status=GroundingStatus.SUPPORTED)

        gen_req = GenerationRequest(query="Hash table speed", scope=self.scope, mode=GenerationMode.QA)
        gen_res = GenerationResult(
            mode=GenerationMode.QA,
            answer="Hash tables have O(1) average lookups [S1].",
            claims=[claim],
            citations={"S1": src},
            overall_grounding_status=GroundingStatus.SUPPORTED,
            model_metadata=None,
        )
        req = EvaluationRequest(
            generation_request=gen_req,
            generation_result=gen_res,
            context_sources={"S1": src},
        )

        # Deepcopy to verify immutability
        original_req_dump = copy.deepcopy(req.model_dump())

        # First run
        run1 = await engine.evaluate(req)
        # Second run
        run2 = await engine.evaluate(req)

        # Immutability check
        self.assertEqual(req.model_dump(), original_req_dump)

        # Determinism check
        self.assertEqual(run1.overall_passed, run2.overall_passed)
        self.assertEqual(run1.overall_score, run2.overall_score)
        self.assertEqual(run1.verdict, run2.verdict)
        self.assertEqual(len(run1.metrics), len(run2.metrics))
        for m1, m2 in zip(run1.metrics, run2.metrics):
            self.assertEqual(m1.name, m2.name)
            self.assertEqual(m1.score, m2.score)
            self.assertEqual(m1.passed, m2.passed)
            self.assertEqual(m1.reason, m2.reason)


if __name__ == "__main__":
    unittest.main()
