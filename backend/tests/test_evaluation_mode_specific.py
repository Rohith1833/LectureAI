"""
Phase 8F-4 — Mode-Specific Evaluators Unit Tests

Tests validating:
- ComparisonEvaluator (subject coverage, dimension coverage, table completeness, similarity/difference balance, mode isolation)
- StudyGuideEvaluator (content completeness, question count fidelity, question deduplication, mode isolation)
"""

import unittest
from app.schemas.generation import (
    GenerationMode,
    GenerationRequest,
    GenerationResult,
    GroundingStatus,
    ContextSource,
    ComparisonOptions,
    StudyGuideOptions,
)
from app.schemas.retrieval import RetrievalScope
from app.schemas.evaluation import EvaluationRequest
from app.services.evaluation.evaluators.comparison import ComparisonEvaluator
from app.services.evaluation.evaluators.study_guide import StudyGuideEvaluator


def make_src(citation_id: str, title: str, content: str) -> ContextSource:
    return ContextSource(
        citation_id=citation_id,
        entity_id=f"ent_{citation_id}",
        title=title,
        entity_type="CONCEPT",
        content=content,
        passage=None,
        provenance="Page 1",
    )


class TestModeSpecificEvaluators(unittest.IsolatedAsyncioTestCase):
    """Unit tests for Phase 8F-4 Comparison and Study Guide evaluators."""

    def setUp(self):
        self.scope = RetrievalScope(document_id="doc_modes", version_id="v_1")

    # =========================================================================
    # 1. ComparisonEvaluator Tests
    # =========================================================================

    async def test_01_comparison_full_subject_and_dimension_coverage(self):
        """Verify ComparisonEvaluator scores 1.0 when all subjects and dimensions are covered."""
        evaluator = ComparisonEvaluator()
        struct = {
            "title": "Merge Sort vs Quick Sort",
            "subjects": ["Merge Sort", "Quick Sort"],
            "comparison_table": [
                {
                    "dimension": "Time Complexity",
                    "values": [
                        {"subject": "Merge Sort", "value": "O(n log n)", "citation_ids": []},
                        {"subject": "Quick Sort", "value": "O(n log n)", "citation_ids": []},
                    ],
                }
            ],
            "similarities": [{"text": "Both are O(n log n) average."}],
            "differences": [{"text": "Merge sort uses extra memory."}],
        }
        req = EvaluationRequest(
            generation_request=GenerationRequest(
                query="Compare sorts",
                scope=self.scope,
                mode=GenerationMode.COMPARISON,
                comparison_options=ComparisonOptions(subjects=["Merge Sort", "Quick Sort"], dimensions=["Time Complexity"]),
            ),
            generation_result=GenerationResult(
                mode=GenerationMode.COMPARISON,
                answer="Comparison Overview",
                claims=[],
                citations={},
                overall_grounding_status=GroundingStatus.SUPPORTED,
                model_metadata=None,
                structured_output=struct,
            ),
        )
        scores = await evaluator.evaluate(req)
        self.assertEqual(len(scores), 4)

        subj_metric = next(s for s in scores if s.name == "comparison_subject_coverage")
        dim_metric = next(s for s in scores if s.name == "comparison_dimension_coverage")
        table_metric = next(s for s in scores if s.name == "comparison_table_completeness")
        balance_metric = next(s for s in scores if s.name == "comparison_similarity_difference_balance")

        self.assertEqual(subj_metric.score, 1.0)
        self.assertTrue(subj_metric.passed)
        self.assertEqual(dim_metric.score, 1.0)
        self.assertTrue(dim_metric.passed)
        self.assertEqual(table_metric.score, 1.0)
        self.assertTrue(table_metric.passed)
        self.assertEqual(balance_metric.score, 1.0)
        self.assertTrue(balance_metric.passed)

    async def test_02_comparison_missing_one_subject(self):
        """Verify ComparisonEvaluator detects missing requested subject."""
        evaluator = ComparisonEvaluator()
        struct = {
            "title": "Merge Sort Only",
            "subjects": ["Merge Sort"],  # Missing Quick Sort
            "comparison_table": [
                {
                    "dimension": "Time Complexity",
                    "values": [{"subject": "Merge Sort", "value": "O(n log n)"}],
                }
            ],
            "similarities": [],
            "differences": [],
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
                answer="Comparison",
                claims=[],
                citations={},
                overall_grounding_status=GroundingStatus.UNSUPPORTED,
                model_metadata=None,
                structured_output=struct,
            ),
        )
        scores = await evaluator.evaluate(req)
        subj_metric = next(s for s in scores if s.name == "comparison_subject_coverage")
        self.assertEqual(subj_metric.score, 0.5)
        self.assertFalse(subj_metric.passed)
        self.assertIn("Quick Sort", subj_metric.reason)

    async def test_03_comparison_mode_isolation(self):
        """Verify ComparisonEvaluator returns empty list for non-comparison modes."""
        evaluator = ComparisonEvaluator()
        req = EvaluationRequest(
            generation_request=GenerationRequest(query="What is X?", scope=self.scope, mode=GenerationMode.QA),
            generation_result=GenerationResult(
                mode=GenerationMode.QA,
                answer="Answer text",
                claims=[],
                citations={},
                overall_grounding_status=GroundingStatus.SUPPORTED,
                model_metadata=None,
            ),
        )
        scores = await evaluator.evaluate(req)
        self.assertEqual(scores, [])

    # =========================================================================
    # 2. StudyGuideEvaluator Tests
    # =========================================================================

    async def test_04_study_guide_full_content_and_question_coverage(self):
        """Verify StudyGuideEvaluator scores 1.0 when content and question counts match."""
        evaluator = StudyGuideEvaluator()
        struct = {
            "title": "BST Study Guide",
            "answer": "Comprehensive overview of Binary Search Trees data structure.",
            "key_concepts": [
                {"concept": "BST", "definition": "A binary tree with key ordering property."}
            ],
            "learning_objectives": ["Identify tree structures", "Analyze lookup complexity"],
            "review_questions": [
                {"question": f"Question {i+1}?", "answer": f"Answer {i+1}", "explanation": "Rationale"}
                for i in range(3)
            ],
        }
        req = EvaluationRequest(
            generation_request=GenerationRequest(
                query="Study BST",
                scope=self.scope,
                mode=GenerationMode.STUDY_GUIDE,
                study_options=StudyGuideOptions(question_count=3, difficulty="intermediate"),
            ),
            generation_result=GenerationResult(
                mode=GenerationMode.STUDY_GUIDE,
                answer="Overview",
                claims=[],
                citations={},
                overall_grounding_status=GroundingStatus.SUPPORTED,
                model_metadata=None,
                structured_output=struct,
            ),
        )
        scores = await evaluator.evaluate(req)
        self.assertEqual(len(scores), 2)

        content_metric = next(s for s in scores if s.name == "study_guide_content_coverage")
        q_metric = next(s for s in scores if s.name == "study_guide_question_coverage")

        self.assertEqual(content_metric.score, 1.0)
        self.assertTrue(content_metric.passed)
        self.assertEqual(q_metric.score, 1.0)
        self.assertTrue(q_metric.passed)

    async def test_05_study_guide_partial_question_count_and_duplicates(self):
        """Verify StudyGuideEvaluator detects fewer questions and penalizes duplicate question text."""
        evaluator = StudyGuideEvaluator()
        struct = {
            "title": "Study Guide",
            "answer": "Overview text for study guide.",
            "key_concepts": [{"concept": "Concept", "definition": "Definition"}],
            "learning_objectives": ["Obj 1"],
            "review_questions": [
                {"question": "What is a tree?", "answer": "A node hierarchy."},
                {"question": "What is a tree?", "answer": "Duplicate question."},  # Duplicate!
            ],
        }
        req = EvaluationRequest(
            generation_request=GenerationRequest(
                query="Study",
                scope=self.scope,
                mode=GenerationMode.STUDY_GUIDE,
                study_options=StudyGuideOptions(question_count=4, difficulty="basic"),  # Requested 4
            ),
            generation_result=GenerationResult(
                mode=GenerationMode.STUDY_GUIDE,
                answer="Overview",
                claims=[],
                citations={},
                overall_grounding_status=GroundingStatus.PARTIALLY_SUPPORTED,
                model_metadata=None,
                structured_output=struct,
            ),
        )
        scores = await evaluator.evaluate(req)
        q_metric = next(s for s in scores if s.name == "study_guide_question_coverage")

        # 1 unique valid question out of 4 requested = 1/4 = 0.25
        self.assertEqual(q_metric.score, 0.25)
        self.assertFalse(q_metric.passed)
        self.assertIn("1 duplicates detected", q_metric.reason)

    async def test_06_study_guide_mode_isolation(self):
        """Verify StudyGuideEvaluator returns empty list for non-study-guide modes."""
        evaluator = StudyGuideEvaluator()
        req = EvaluationRequest(
            generation_request=GenerationRequest(query="Compare A and B", scope=self.scope, mode=GenerationMode.COMPARISON, comparison_options=ComparisonOptions(subjects=["A", "B"])),
            generation_result=GenerationResult(
                mode=GenerationMode.COMPARISON,
                answer="Comparison",
                claims=[],
                citations={},
                overall_grounding_status=GroundingStatus.SUPPORTED,
                model_metadata=None,
                structured_output={"title": "Comparison", "subjects": ["A", "B"], "comparison_table": [], "similarities": [], "differences": []},
            ),
        )
        scores = await evaluator.evaluate(req)
        self.assertEqual(scores, [])


if __name__ == "__main__":
    unittest.main()
