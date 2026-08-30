"""
Phase 8F-4 — Benchmark Harness & Golden Dataset Unit Tests

Tests validating:
- BenchmarkRunner execution on empty, single, and multiple cases
- Full execution across the 12-case Golden Dataset
- Aggregate metric scores, verdict rollups, and mode-level score breakdowns
- Accurate identification of failing benchmark cases
- Strict determinism and immutability across repeated benchmark runs
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
)
from app.schemas.retrieval import RetrievalScope
from app.schemas.evaluation import EvaluationVerdict
from app.services.evaluation.benchmark import EvaluationCase, BenchmarkRunner
from tests.fixtures.evaluation.golden_dataset import get_golden_dataset


class TestEvaluationBenchmark(unittest.IsolatedAsyncioTestCase):
    """Unit tests for BenchmarkRunner and golden benchmark dataset execution."""

    def setUp(self):
        self.scope = RetrievalScope(document_id="doc_bench", version_id="v_1")

    async def test_01_benchmark_runner_empty_cases(self):
        """Verify BenchmarkRunner safely handles empty case list."""
        runner = BenchmarkRunner()
        report = await runner.run([])
        self.assertEqual(report.total_cases, 0)
        self.assertEqual(report.passed_cases, 0)
        self.assertEqual(report.failed_cases, 0)
        self.assertEqual(report.pass_rate, 1.0)
        self.assertEqual(report.average_overall_score, 1.0)
        self.assertEqual(report.failed_case_ids, [])

    async def test_02_benchmark_runner_single_case(self):
        """Verify BenchmarkRunner executes a single test case correctly."""
        runner = BenchmarkRunner()
        src = ContextSource(
            citation_id="S1",
            entity_id="ent_1",
            title="Quicksort",
            entity_type="CONCEPT",
            content="Quicksort is an efficient sorting algorithm.",
            passage=None,
            provenance="Page 1",
        )
        case = EvaluationCase(
            id="single_test_case",
            description="Single test case",
            generation_request=GenerationRequest(query="What is quicksort?", scope=self.scope, mode=GenerationMode.QA),
            generation_result=GenerationResult(
                mode=GenerationMode.QA,
                answer="Quicksort is an efficient sorting algorithm [S1].",
                claims=[
                    GenerationClaim(claim_id="c1", text="Quicksort is an efficient sorting algorithm.", citation_ids=["S1"], grounding_status=GroundingStatus.SUPPORTED)
                ],
                citations={"S1": src},
                overall_grounding_status=GroundingStatus.SUPPORTED,
                model_metadata=None,
            ),
            context_sources={"S1": src},
        )
        report = await runner.run([case])
        self.assertEqual(report.total_cases, 1)
        self.assertEqual(report.passed_cases, 1)
        self.assertEqual(report.failed_cases, 0)
        self.assertEqual(report.pass_rate, 1.0)
        self.assertGreaterEqual(report.average_overall_score, 0.90)
        self.assertEqual(report.verdict_counts["PASS"], 1)

    async def test_03_benchmark_runner_golden_dataset_full_execution(self):
        """Verify BenchmarkRunner processes the full 12-case golden dataset."""
        runner = BenchmarkRunner()
        dataset = get_golden_dataset()
        self.assertEqual(len(dataset), 12)

        report = await runner.run(dataset)
        self.assertEqual(report.total_cases, 12)
        # Expected: 6 passed (cases 1, 4, 5, 6, 8, 10), 6 intentionally failing/malformed (cases 2, 3, 7, 9, 11, 12)
        self.assertEqual(report.passed_cases, 6)
        self.assertEqual(report.failed_cases, 6)
        self.assertEqual(report.pass_rate, 0.50)
        self.assertGreater(report.average_overall_score, 0.40)
        self.assertLess(report.average_overall_score, 0.85)

        # Verify metric aggregates are populated
        self.assertIn("schema_compliance_score", report.metric_aggregates)
        self.assertIn("citation_validity_rate", report.metric_aggregates)
        self.assertIn("empty_abstention_accuracy", report.metric_aggregates)
        self.assertIn("claim_faithfulness_score", report.metric_aggregates)
        self.assertIn("answer_relevance_score", report.metric_aggregates)

    async def test_04_benchmark_runner_mode_breakdowns(self):
        """Verify BenchmarkRunner computes separated scores for each mode."""
        runner = BenchmarkRunner()
        dataset = get_golden_dataset()
        report = await runner.run(dataset)

        self.assertIn("QA", report.mode_scores)
        self.assertIn("EXPLANATION", report.mode_scores)
        self.assertIn("SUMMARY", report.mode_scores)
        self.assertIn("COMPARISON", report.mode_scores)
        self.assertIn("STUDY_GUIDE", report.mode_scores)

        # Grounded single-mode cases have high scores
        self.assertGreaterEqual(report.mode_scores["EXPLANATION"], 0.85)
        self.assertGreaterEqual(report.mode_scores["SUMMARY"], 0.85)

    async def test_05_benchmark_runner_failed_cases_identification(self):
        """Verify BenchmarkRunner identifies the exact failing test cases."""
        runner = BenchmarkRunner()
        dataset = get_golden_dataset()
        report = await runner.run(dataset)

        expected_failures = {
            "case_02_qa_unsupported",
            "case_03_qa_invalid_citation",
            "case_07_abstention_failed",
            "case_09_comparison_missing_subject",
            "case_11_study_guide_missing_questions",
            "case_12_structural_malformed",
        }
        self.assertEqual(set(report.failed_case_ids), expected_failures)

    async def test_06_benchmark_runner_determinism_and_immutability(self):
        """Verify repeated runs on identical dataset produce exact same metrics and do not mutate cases."""
        runner = BenchmarkRunner()
        dataset = get_golden_dataset()
        dataset_copy = copy.deepcopy([c.model_dump() for c in dataset])

        report1 = await runner.run(dataset)
        report2 = await runner.run(dataset)

        # Immutability
        self.assertEqual([c.model_dump() for c in dataset], dataset_copy)

        # Determinism
        self.assertEqual(report1.total_cases, report2.total_cases)
        self.assertEqual(report1.passed_cases, report2.passed_cases)
        self.assertEqual(report1.failed_cases, report2.failed_cases)
        self.assertEqual(report1.pass_rate, report2.pass_rate)
        self.assertEqual(report1.average_overall_score, report2.average_overall_score)
        self.assertEqual(report1.verdict_counts, report2.verdict_counts)
        self.assertEqual(report1.metric_aggregates, report2.metric_aggregates)
        self.assertEqual(report1.mode_scores, report2.mode_scores)
        self.assertEqual(report1.failed_case_ids, report2.failed_case_ids)


if __name__ == "__main__":
    unittest.main()
