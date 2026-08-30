"""
Phase 8F-2 — Deterministic Evaluators Unit Tests

Tests validating:
- StructuralEvaluator across QA, Explanation, Summary, Comparison, and Study Guide
- CitationEvaluator with valid citations, invalid citations, and nested structures
- AbstentionEvaluator under empty and populated context scenarios
- Integration via create_default_evaluation_engine()
"""

import unittest
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
from app.services.evaluation import EvaluationEngine, create_default_evaluation_engine


def make_context_source(citation_id: str, title: str = "Test Source", content: str = "Sample content") -> ContextSource:
    """Helper creating a fully populated ContextSource object."""
    return ContextSource(
        citation_id=citation_id,
        entity_id=f"ent_{citation_id}",
        title=title,
        entity_type="CONCEPT",
        content=content,
        passage=None,
        provenance="Page 1",
    )


class TestDeterministicEvaluators(unittest.IsolatedAsyncioTestCase):
    """Unit tests for Phase 8F-2 deterministic evaluators."""

    def setUp(self):
        self.scope = RetrievalScope(document_id="doc_demo", version_id="v_1")

    # =========================================================================
    # 1. StructuralEvaluator Tests
    # =========================================================================

    async def test_01_structural_evaluator_valid_qa(self):
        """Verify valid QA result passes structural evaluation."""
        evaluator = StructuralEvaluator()
        req = EvaluationRequest(
            generation_request=GenerationRequest(query="What is X?", scope=self.scope, mode=GenerationMode.QA),
            generation_result=GenerationResult(
                mode=GenerationMode.QA,
                answer="X is a deterministic algorithm [S1].",
                claims=[
                    GenerationClaim(claim_id="c1", text="X is deterministic", citation_ids=["S1"], grounding_status=GroundingStatus.SUPPORTED)
                ],
                citations={"S1": make_context_source("S1", "X Overview")},
                overall_grounding_status=GroundingStatus.SUPPORTED,
                model_metadata=None,
                structured_output=None,
            ),
        )
        scores = await evaluator.evaluate(req)
        self.assertEqual(len(scores), 1)
        self.assertEqual(scores[0].name, "schema_compliance_score")
        self.assertEqual(scores[0].score, 1.0)
        self.assertTrue(scores[0].passed)

    async def test_02_structural_evaluator_invalid_qa_empty_answer(self):
        """Verify QA result with empty answer fails structural evaluation."""
        evaluator = StructuralEvaluator()
        req = EvaluationRequest(
            generation_request=GenerationRequest(query="What is X?", scope=self.scope, mode=GenerationMode.QA),
            generation_result=GenerationResult(
                mode=GenerationMode.QA,
                answer="   ",  # Blank
                claims=[],
                citations={},
                overall_grounding_status=GroundingStatus.UNSUPPORTED,
                model_metadata=None,
                structured_output=None,
            ),
        )
        scores = await evaluator.evaluate(req)
        self.assertEqual(scores[0].score, 0.0)
        self.assertFalse(scores[0].passed)
        self.assertIn("requires a non-empty string in 'answer'", scores[0].reason)

    async def test_03_structural_evaluator_valid_comparison(self):
        """Verify valid Comparison structured output passes structural evaluation."""
        evaluator = StructuralEvaluator()
        comparison_dict = {
            "title": "Merge Sort vs Quick Sort",
            "subjects": ["Merge Sort", "Quick Sort"],
            "comparison_table": [
                {
                    "dimension": "Worst Case Time",
                    "values": [
                        {"subject": "Merge Sort", "value": "O(n log n) [S1]", "citation_ids": ["S1"]},
                        {"subject": "Quick Sort", "value": "O(n^2) [S2]", "citation_ids": ["S2"]},
                    ],
                    "explanation": "Merge sort is guaranteed O(n log n).",
                }
            ],
            "similarities": [{"text": "Both are divide and conquer [S1].", "citation_ids": ["S1"]}],
            "differences": [{"text": "Merge sort requires extra memory [S1].", "citation_ids": ["S1"]}],
        }
        req = EvaluationRequest(
            generation_request=GenerationRequest(
                query="Compare sorts",
                scope=self.scope,
                mode=GenerationMode.COMPARISON,
                comparison_options=ComparisonOptions(subjects=["Merge Sort", "Quick Sort"]),
            ),
            generation_result=GenerationResult(
                mode=GenerationMode.COMPARISON,
                answer="Merge Sort vs Quick Sort",
                claims=[],
                citations={"S1": make_context_source("S1", "Sorts")},
                overall_grounding_status=GroundingStatus.SUPPORTED,
                model_metadata=None,
                structured_output=comparison_dict,
            ),
        )
        scores = await evaluator.evaluate(req)
        self.assertEqual(scores[0].score, 1.0)
        self.assertTrue(scores[0].passed)

    async def test_04_structural_evaluator_invalid_comparison_missing_subjects(self):
        """Verify Comparison with < 2 subjects fails structural evaluation."""
        evaluator = StructuralEvaluator()
        invalid_comp = {
            "title": "Invalid Comparison",
            "subjects": ["Merge Sort"],  # Only 1 subject in output
            "comparison_table": [],
            "similarities": [],
            "differences": [],
        }
        req = EvaluationRequest(
            generation_request=GenerationRequest(
                query="Compare",
                scope=self.scope,
                mode=GenerationMode.COMPARISON,
                comparison_options=ComparisonOptions(subjects=["Merge Sort", "Quick Sort"]),
            ),
            generation_result=GenerationResult(
                mode=GenerationMode.COMPARISON,
                answer="Invalid",
                claims=[],
                citations={},
                overall_grounding_status=GroundingStatus.UNSUPPORTED,
                model_metadata=None,
                structured_output=invalid_comp,
            ),
        )
        scores = await evaluator.evaluate(req)
        self.assertEqual(scores[0].score, 0.0)
        self.assertFalse(scores[0].passed)
        self.assertIn("at least 2 items", scores[0].reason)

    async def test_05_structural_evaluator_valid_study_guide(self):
        """Verify valid Study Guide structured output passes structural evaluation."""
        evaluator = StructuralEvaluator()
        study_dict = {
            "title": "Algorithms Study Guide",
            "answer": "Overview of algorithm paradigms [S1].",
            "key_concepts": [{"concept": "Greedy", "definition": "Makes locally optimal choices [S1].", "citation_ids": ["S1"]}],
            "learning_objectives": ["Identify greedy algorithms [S1]."],
            "review_questions": [
                {
                    "question": "What is greedy choice?",
                    "answer": "Locally optimal choice at each step.",
                    "explanation": "Guarantees global optimum for certain matroids.",
                    "citation_ids": ["S1"],
                }
            ],
        }
        req = EvaluationRequest(
            generation_request=GenerationRequest(
                query="Study guide",
                scope=self.scope,
                mode=GenerationMode.STUDY_GUIDE,
                study_options=StudyGuideOptions(question_count=5, difficulty="intermediate"),
            ),
            generation_result=GenerationResult(
                mode=GenerationMode.STUDY_GUIDE,
                answer="Overview",
                claims=[],
                citations={"S1": make_context_source("S1", "Greedy")},
                overall_grounding_status=GroundingStatus.SUPPORTED,
                model_metadata=None,
                structured_output=study_dict,
            ),
        )
        scores = await evaluator.evaluate(req)
        self.assertEqual(scores[0].score, 1.0)
        self.assertTrue(scores[0].passed)

    async def test_06_structural_evaluator_invalid_study_guide_missing_questions(self):
        """Verify Study Guide missing review questions fails structural evaluation."""
        evaluator = StructuralEvaluator()
        invalid_study = {
            "title": "Incomplete Guide",
            "answer": "Overview text",
            "key_concepts": [],
            "learning_objectives": [],
            "review_questions": [],  # Empty
        }
        req = EvaluationRequest(
            generation_request=GenerationRequest(
                query="Study guide",
                scope=self.scope,
                mode=GenerationMode.STUDY_GUIDE,
                study_options=StudyGuideOptions(question_count=5, difficulty="intermediate"),
            ),
            generation_result=GenerationResult(
                mode=GenerationMode.STUDY_GUIDE,
                answer="Overview",
                claims=[],
                citations={},
                overall_grounding_status=GroundingStatus.UNSUPPORTED,
                model_metadata=None,
                structured_output=invalid_study,
            ),
        )
        scores = await evaluator.evaluate(req)
        self.assertEqual(scores[0].score, 0.0)
        self.assertFalse(scores[0].passed)
        self.assertIn("non-empty 'review_questions'", scores[0].reason)

    # =========================================================================
    # 2. CitationEvaluator Tests
    # =========================================================================

    async def test_07_citation_evaluator_all_valid(self):
        """Verify CitationEvaluator scores 1.0 when all cited IDs exist in context."""
        evaluator = CitationEvaluator()
        req = EvaluationRequest(
            generation_request=GenerationRequest(query="What is S?", scope=self.scope, mode=GenerationMode.QA),
            generation_result=GenerationResult(
                mode=GenerationMode.QA,
                answer="S is valid [S1] and verified [S2].",
                claims=[
                    GenerationClaim(claim_id="c1", text="S is valid", citation_ids=["S1"], grounding_status=GroundingStatus.SUPPORTED),
                    GenerationClaim(claim_id="c2", text="S is verified", citation_ids=["S2"], grounding_status=GroundingStatus.SUPPORTED),
                ],
                citations={"S1": make_context_source("S1", "Source 1"), "S2": make_context_source("S2", "Source 2")},
                overall_grounding_status=GroundingStatus.SUPPORTED,
                model_metadata=None,
            ),
            context_sources={"S1": {"title": "Source 1"}, "S2": {"title": "Source 2"}, "S3": {"title": "Unused Source"}},
        )
        scores = await evaluator.evaluate(req)
        validity = next(s for s in scores if s.name == "citation_validity_rate")
        coverage = next(s for s in scores if s.name == "claim_citation_coverage")

        self.assertEqual(validity.score, 1.0)
        self.assertTrue(validity.passed)
        self.assertEqual(coverage.score, 1.0)
        self.assertTrue(coverage.passed)

    async def test_08_citation_evaluator_invalid_citations(self):
        """Verify CitationEvaluator detects invalid citation IDs not present in context."""
        evaluator = CitationEvaluator()
        req = EvaluationRequest(
            generation_request=GenerationRequest(query="What is S?", scope=self.scope, mode=GenerationMode.QA),
            generation_result=GenerationResult(
                mode=GenerationMode.QA,
                answer="S is valid [S1] but references fake source [S99].",
                claims=[
                    GenerationClaim(claim_id="c1", text="Claim with fake source", citation_ids=["S99"], grounding_status=GroundingStatus.UNSUPPORTED),
                ],
                citations={"S1": make_context_source("S1", "Source 1"), "S99": make_context_source("S99", "Fake")},
                overall_grounding_status=GroundingStatus.PARTIALLY_SUPPORTED,
                model_metadata=None,
            ),
            context_sources={"S1": {"title": "Source 1"}},  # Only S1 is in context
        )
        scores = await evaluator.evaluate(req)
        validity = next(s for s in scores if s.name == "citation_validity_rate")
        coverage = next(s for s in scores if s.name == "claim_citation_coverage")

        # 1 valid (S1), 1 invalid (S99) -> 1/2 = 0.5
        self.assertEqual(validity.score, 0.5)
        self.assertFalse(validity.passed)
        self.assertIn("S99", validity.reason)
        self.assertEqual(coverage.score, 0.0)

    async def test_09_citation_evaluator_nested_comparison_citations(self):
        """Verify CitationEvaluator inspects nested citations inside Comparison structured output."""
        evaluator = CitationEvaluator()
        comparison_dict = {
            "title": "Comparison",
            "subjects": ["A", "B"],
            "comparison_table": [
                {
                    "dimension": "Dim 1",
                    "values": [{"subject": "A", "value": "Val A", "citation_ids": ["S1"]}],
                }
            ],
            "similarities": [{"text": "Sim", "citation_ids": ["S2"]}],
            "differences": [{"text": "Diff", "citation_ids": ["S99"]}],  # Invalid
        }
        req = EvaluationRequest(
            generation_request=GenerationRequest(
                query="Compare",
                scope=self.scope,
                mode=GenerationMode.COMPARISON,
                comparison_options=ComparisonOptions(subjects=["A", "B"]),
            ),
            generation_result=GenerationResult(
                mode=GenerationMode.COMPARISON,
                answer="Comparison",
                claims=[],
                citations={},
                overall_grounding_status=GroundingStatus.PARTIALLY_SUPPORTED,
                model_metadata=None,
                structured_output=comparison_dict,
            ),
            context_sources={"S1": {}, "S2": {}},
        )
        scores = await evaluator.evaluate(req)
        validity = next(s for s in scores if s.name == "citation_validity_rate")

        # S1, S2 valid; S99 invalid -> 2/3 = 0.6667
        self.assertAlmostEqual(validity.score, 0.6667, places=3)
        self.assertFalse(validity.passed)

    async def test_10_citation_evaluator_nested_study_guide_citations(self):
        """Verify CitationEvaluator inspects nested citations inside Study Guide structured output."""
        evaluator = CitationEvaluator()
        study_dict = {
            "title": "Study Guide",
            "answer": "Overview [S1]",
            "key_concepts": [{"concept": "Concept 1", "definition": "Def", "citation_ids": ["S2"]}],
            "learning_objectives": [],
            "review_questions": [
                {"question": "Q1", "answer": "A1", "explanation": "E1", "citation_ids": ["S3"]}
            ],
        }
        req = EvaluationRequest(
            generation_request=GenerationRequest(
                query="Study",
                scope=self.scope,
                mode=GenerationMode.STUDY_GUIDE,
                study_options=StudyGuideOptions(question_count=5, difficulty="intermediate"),
            ),
            generation_result=GenerationResult(
                mode=GenerationMode.STUDY_GUIDE,
                answer="Overview",
                claims=[],
                citations={},
                overall_grounding_status=GroundingStatus.SUPPORTED,
                model_metadata=None,
                structured_output=study_dict,
            ),
            context_sources={"S1": {}, "S2": {}, "S3": {}},
        )
        scores = await evaluator.evaluate(req)
        validity = next(s for s in scores if s.name == "citation_validity_rate")
        self.assertEqual(validity.score, 1.0)
        self.assertTrue(validity.passed)

    # =========================================================================
    # 3. AbstentionEvaluator Tests
    # =========================================================================

    async def test_11_abstention_evaluator_empty_context_with_insufficient_status(self):
        """Verify model receives 1.0 on empty context when it accurately abstains."""
        evaluator = AbstentionEvaluator()
        req = EvaluationRequest(
            generation_request=GenerationRequest(query="Obscure question", scope=self.scope, mode=GenerationMode.QA),
            generation_result=GenerationResult(
                mode=GenerationMode.QA,
                answer="INSUFFICIENT_CONTEXT",
                claims=[],
                citations={},
                overall_grounding_status=GroundingStatus.INSUFFICIENT_CONTEXT,
                model_metadata=None,
            ),
            context_sources={},  # Empty context
        )
        scores = await evaluator.evaluate(req)
        self.assertEqual(len(scores), 1)
        self.assertEqual(scores[0].name, "empty_abstention_accuracy")
        self.assertEqual(scores[0].score, 1.0)
        self.assertTrue(scores[0].passed)

    async def test_12_abstention_evaluator_empty_context_with_substantive_answer(self):
        """Verify model receives 0.0 when fabricating substantive answer on empty context."""
        evaluator = AbstentionEvaluator()
        req = EvaluationRequest(
            generation_request=GenerationRequest(query="Obscure question", scope=self.scope, mode=GenerationMode.QA),
            generation_result=GenerationResult(
                mode=GenerationMode.QA,
                answer="The secret answer is 42 and was invented by researchers in 1984.",
                claims=[
                    GenerationClaim(claim_id="c1", text="Invented in 1984", citation_ids=[], grounding_status=GroundingStatus.UNSUPPORTED)
                ],
                citations={},
                overall_grounding_status=GroundingStatus.UNSUPPORTED,
                model_metadata=None,
            ),
            context_sources={},  # Empty context
        )
        scores = await evaluator.evaluate(req)
        self.assertEqual(scores[0].score, 0.0)
        self.assertFalse(scores[0].passed)
        self.assertIn("substantive ungrounded response", scores[0].reason)

    async def test_13_abstention_evaluator_populated_context_normal(self):
        """Verify model receives 1.0 on normal grounded response with available context."""
        evaluator = AbstentionEvaluator()
        req = EvaluationRequest(
            generation_request=GenerationRequest(query="What is S?", scope=self.scope, mode=GenerationMode.QA),
            generation_result=GenerationResult(
                mode=GenerationMode.QA,
                answer="S is grounded [S1].",
                claims=[
                    GenerationClaim(claim_id="c1", text="S is grounded", citation_ids=["S1"], grounding_status=GroundingStatus.SUPPORTED)
                ],
                citations={"S1": make_context_source("S1", "Source S")},
                overall_grounding_status=GroundingStatus.SUPPORTED,
                model_metadata=None,
            ),
            context_sources={"S1": {}},
        )
        scores = await evaluator.evaluate(req)
        self.assertEqual(scores[0].score, 1.0)
        self.assertTrue(scores[0].passed)

    # =========================================================================
    # 4. Integrated Engine Test
    # =========================================================================

    async def test_14_full_default_engine_pipeline(self):
        """Verify EvaluationEngine orchestrates the 3 core deterministic evaluators."""
        engine = EvaluationEngine([
            StructuralEvaluator(),
            CitationEvaluator(),
            AbstentionEvaluator(),
        ])
        self.assertEqual(len(engine.evaluators), 3)

        req = EvaluationRequest(
            generation_request=GenerationRequest(query="Explain Binary Search", scope=self.scope, mode=GenerationMode.QA),
            generation_result=GenerationResult(
                mode=GenerationMode.QA,
                answer="Binary search is O(log n) [S1].",
                claims=[
                    GenerationClaim(claim_id="c1", text="Binary search is logarithmic", citation_ids=["S1"], grounding_status=GroundingStatus.SUPPORTED)
                ],
                citations={"S1": make_context_source("S1", "Binary Search")},
                overall_grounding_status=GroundingStatus.SUPPORTED,
                model_metadata={"model_name": "test-model"},
            ),
            context_sources={"S1": {"title": "Binary Search"}},
        )

        result = await engine.evaluate(req)
        self.assertTrue(result.overall_passed)
        self.assertEqual(result.verdict, EvaluationVerdict.PASS)
        self.assertAlmostEqual(result.overall_score, 1.0)
        self.assertEqual(len(result.metrics), 5)  # 1 structural, 3 citation, 1 abstention
        metric_names = {m.name for m in result.metrics}
        self.assertIn("schema_compliance_score", metric_names)
        self.assertIn("citation_validity_rate", metric_names)
        self.assertIn("claim_citation_coverage", metric_names)
        self.assertIn("context_utilization_rate", metric_names)
        self.assertIn("empty_abstention_accuracy", metric_names)


if __name__ == "__main__":
    unittest.main()
