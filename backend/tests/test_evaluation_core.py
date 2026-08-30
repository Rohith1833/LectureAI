"""
Phase 8F-1 — Generation Evaluation Core & Schemas Tests

Tests validating:
- MetricScore validation and boundary checks
- EvaluationRequest & EvaluationResult serialization
- BaseEvaluator protocol and implementation
- EvaluationEngine orchestration, weighting, and verdict generation
- Error isolation during evaluation execution
"""

import unittest
from typing import List
from app.schemas.generation import (
    GenerationMode,
    GenerationRequest,
    GenerationResult,
    GroundingStatus,
)
from app.schemas.retrieval import RetrievalScope
from app.schemas.evaluation import (
    EvaluationVerdict,
    MetricScore,
    EvaluationRequest,
    EvaluationResult,
)
from app.services.evaluation.base import BaseEvaluator
from app.services.evaluation.engine import EvaluationEngine


class DummyPassingEvaluator(BaseEvaluator):
    @property
    def name(self) -> str:
        return "dummy_passing"

    async def evaluate(self, request: EvaluationRequest) -> List[MetricScore]:
        return [
            MetricScore(
                name="dummy_accuracy",
                score=0.95,
                threshold=0.80,
                passed=True,
                weight=2.0,
                reason="High accuracy observed.",
            ),
            MetricScore(
                name="dummy_citation_rate",
                score=1.0,
                threshold=0.90,
                passed=True,
                weight=1.0,
                reason="All citations valid.",
            ),
        ]


class DummyFailingEvaluator(BaseEvaluator):
    @property
    def name(self) -> str:
        return "dummy_failing"

    async def evaluate(self, request: EvaluationRequest) -> List[MetricScore]:
        return [
            MetricScore(
                name="dummy_grounding",
                score=0.40,
                threshold=0.75,
                passed=False,
                weight=3.0,
                reason="Hallucination detected in statement 2.",
            )
        ]


class DummyCrashingEvaluator(BaseEvaluator):
    @property
    def name(self) -> str:
        return "dummy_crashing"

    async def evaluate(self, request: EvaluationRequest) -> List[MetricScore]:
        raise RuntimeError("Unexpected evaluator internal error")


class TestEvaluationCore(unittest.IsolatedAsyncioTestCase):
    """Test suite covering the foundational evaluation schemas, engine, and metrics."""

    def setUp(self):
        self.sample_gen_request = GenerationRequest(
            query="What is quicksort?",
            scope=RetrievalScope(document_id="doc_123"),
            mode=GenerationMode.QA,
        )
        self.sample_gen_result = GenerationResult(
            mode=GenerationMode.QA,
            answer="Quicksort is a divide and conquer algorithm [S1].",
            claims=[],
            citations={},
            overall_grounding_status=GroundingStatus.SUPPORTED,
            model_metadata={"model_name": "test-model"},
            structured_output=None,
        )
        self.eval_request = EvaluationRequest(
            generation_request=self.sample_gen_request,
            generation_result=self.sample_gen_result,
            context_sources={"S1": {"title": "Quicksort Overview"}},
        )

    def test_01_metric_score_bounds_and_validation(self):
        """Verify MetricScore enforces [0.0, 1.0] bounds and non-negative weight."""
        # Valid score
        m = MetricScore(name="test_metric", score=0.85, threshold=0.70, passed=True)
        self.assertEqual(m.score, 0.85)
        self.assertEqual(m.weight, 1.0)
        self.assertTrue(m.passed)

        # Out of bounds score (> 1.0)
        with self.assertRaises(ValueError):
            MetricScore(name="invalid", score=1.2, threshold=0.5, passed=True)

        # Negative score (< 0.0)
        with self.assertRaises(ValueError):
            MetricScore(name="invalid", score=-0.1, threshold=0.5, passed=False)

        # Negative weight
        with self.assertRaises(ValueError):
            MetricScore(name="invalid", score=0.5, threshold=0.5, passed=True, weight=-1.0)

    def test_02_evaluation_request_and_result_schemas(self):
        """Verify EvaluationRequest and EvaluationResult contract serialization."""
        self.assertEqual(self.eval_request.generation_request.query, "What is quicksort?")
        self.assertEqual(self.eval_request.generation_result.mode, GenerationMode.QA)

        res = EvaluationResult(
            mode=GenerationMode.QA,
            overall_passed=True,
            overall_score=0.92,
            verdict=EvaluationVerdict.PASS,
            metrics=[],
            diagnostics={"duration_ms": 12.5},
        )
        self.assertTrue(res.overall_passed)
        self.assertEqual(res.verdict, EvaluationVerdict.PASS)
        self.assertIsInstance(res.evaluation_id, str)
        self.assertGreater(res.evaluated_at, 0)

    def test_03_base_evaluator_subclassing(self):
        """Verify BaseEvaluator abstract contract requires name and evaluate method."""
        evaluator = DummyPassingEvaluator()
        self.assertEqual(evaluator.name, "dummy_passing")

    def test_04_engine_registration_and_unregistration(self):
        """Verify EvaluationEngine registers, queries, and unregisters evaluators."""
        engine = EvaluationEngine()
        self.assertEqual(len(engine.evaluators), 0)

        p_eval = DummyPassingEvaluator()
        engine.register_evaluator(p_eval)
        self.assertEqual(len(engine.evaluators), 1)

        engine.unregister_evaluator("dummy_passing")
        self.assertEqual(len(engine.evaluators), 0)

    async def test_05_engine_evaluation_all_pass(self):
        """Verify engine aggregates passing metrics into overall PASS verdict."""
        engine = EvaluationEngine([DummyPassingEvaluator()])
        result = await engine.evaluate(self.eval_request)

        self.assertEqual(result.mode, GenerationMode.QA)
        self.assertTrue(result.overall_passed)
        self.assertEqual(result.verdict, EvaluationVerdict.PASS)
        self.assertEqual(len(result.metrics), 2)
        # Weighted average: (0.95*2 + 1.0*1) / 3 = 2.9 / 3 = 0.9667
        self.assertAlmostEqual(result.overall_score, 0.9667, places=3)
        self.assertEqual(result.diagnostics["total_metrics"], 2)
        self.assertEqual(result.diagnostics["failed_metrics"], [])

    async def test_06_engine_evaluation_weighted_score(self):
        """Verify engine accurately computes weighted composite score across multiple evaluators."""
        engine = EvaluationEngine([DummyPassingEvaluator(), DummyFailingEvaluator()])
        result = await engine.evaluate(self.eval_request)

        # Metrics:
        # 1. score=0.95, weight=2.0 (1.9)
        # 2. score=1.0,  weight=1.0 (1.0)
        # 3. score=0.40, weight=3.0 (1.2)
        # Total weight = 6.0, Total weighted = 4.1 -> 4.1 / 6.0 = 0.6833
        self.assertAlmostEqual(result.overall_score, 0.6833, places=3)
        self.assertFalse(result.overall_passed)
        self.assertEqual(result.verdict, EvaluationVerdict.FAIL)
        self.assertIn("dummy_grounding", result.diagnostics["failed_metrics"])

    async def test_07_engine_evaluation_warning_verdict(self):
        """Verify engine assigns WARNING verdict when overall score is moderate (0.60 to 0.85)."""
        class ModerateEvaluator(BaseEvaluator):
            @property
            def name(self) -> str:
                return "moderate"

            async def evaluate(self, request: EvaluationRequest) -> List[MetricScore]:
                return [
                    MetricScore(
                        name="moderate_metric",
                        score=0.75,
                        threshold=0.70,
                        passed=True,
                        weight=1.0,
                    )
                ]

        engine = EvaluationEngine([ModerateEvaluator()])
        result = await engine.evaluate(self.eval_request)

        self.assertTrue(result.overall_passed)
        self.assertEqual(result.verdict, EvaluationVerdict.WARNING)
        self.assertEqual(result.overall_score, 0.75)

    async def test_08_engine_evaluation_fail_verdict(self):
        """Verify engine assigns FAIL verdict when any critical metric fails or composite < 0.60."""
        engine = EvaluationEngine([DummyFailingEvaluator()])
        result = await engine.evaluate(self.eval_request)

        self.assertFalse(result.overall_passed)
        self.assertEqual(result.verdict, EvaluationVerdict.FAIL)
        self.assertEqual(result.overall_score, 0.40)

    async def test_09_engine_handles_evaluator_exceptions_gracefully(self):
        """Verify engine catches evaluator exceptions without aborting other evaluations."""
        engine = EvaluationEngine([DummyPassingEvaluator(), DummyCrashingEvaluator()])
        result = await engine.evaluate(self.eval_request)

        # Passing metrics are still collected
        self.assertEqual(len(result.metrics), 2)
        self.assertTrue(result.overall_passed)
        # Diagnostics captures the error
        self.assertEqual(result.diagnostics["evaluator_runs"]["dummy_crashing"]["status"], "ERROR")
        self.assertIn("Unexpected evaluator internal error", result.diagnostics["evaluator_runs"]["dummy_crashing"]["error"])

    async def test_10_empty_engine_returns_clean_result(self):
        """Verify engine with 0 evaluators returns safe default values."""
        engine = EvaluationEngine([])
        result = await engine.evaluate(self.eval_request)

        self.assertTrue(result.overall_passed)
        self.assertEqual(result.overall_score, 1.0)
        self.assertEqual(result.verdict, EvaluationVerdict.PASS)
        self.assertEqual(len(result.metrics), 0)


if __name__ == "__main__":
    unittest.main()
