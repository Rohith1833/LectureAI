"""
Phase 8F-5 — Evaluation Quality Gate & CLI Unit Tests

Tests validating:
- EvaluationQualityGate threshold enforcement (overall score, pass rate, metric minimums)
- Quality regression detection against version-controlled golden baseline
- Unexpected benchmark failure detection
- Benchmark CLI runner execution and JSON machine-readable output
- Quality gate determinism
"""

import io
import json
import unittest
from unittest.mock import patch
from app.services.evaluation.benchmark import BenchmarkReport, BenchmarkRunner
from app.services.evaluation.quality_gate import (
    EvaluationGateConfig,
    EvaluationGateResult,
    EvaluationQualityGate,
)
from app.services.evaluation.run_benchmark import run_benchmark_cli
from tests.fixtures.evaluation.golden_dataset import get_golden_dataset


class TestEvaluationQualityGate(unittest.IsolatedAsyncioTestCase):
    """Unit tests for Phase 8F-5 EvaluationQualityGate and CLI runner."""

    def setUp(self):
        self.sample_report = BenchmarkReport(
            total_cases=10,
            passed_cases=8,
            failed_cases=2,
            pass_rate=0.80,
            average_overall_score=0.88,
            verdict_counts={"PASS": 8, "WARNING": 0, "FAIL": 2},
            metric_aggregates={
                "schema_compliance_score": 0.90,
                "citation_validity_rate": 0.85,
                "empty_abstention_accuracy": 1.0,
            },
            mode_scores={"QA": 0.88},
            failed_case_ids=["case_bad_1", "case_bad_2"],
            case_results=[],
            duration_ms=12.5,
        )

    def test_01_quality_gate_passes_standard_benchmark(self):
        """Verify quality gate passes when all score criteria are satisfied."""
        gate = EvaluationQualityGate(config=EvaluationGateConfig(minimum_overall_score=0.75, minimum_pass_rate=0.70))
        result = gate.evaluate_report(self.sample_report, expected_failed_ids=["case_bad_1", "case_bad_2"])
        self.assertTrue(result.passed)
        self.assertEqual(result.failures, [])
        self.assertEqual(result.current_score, 0.88)

    def test_02_quality_gate_fails_low_overall_score(self):
        """Verify quality gate fails when overall score falls below minimum."""
        gate = EvaluationQualityGate(config=EvaluationGateConfig(minimum_overall_score=0.95))
        result = gate.evaluate_report(self.sample_report, expected_failed_ids=["case_bad_1", "case_bad_2"])
        self.assertFalse(result.passed)
        self.assertTrue(any("below minimum threshold" in f for f in result.failures))

    def test_03_quality_gate_fails_low_pass_rate(self):
        """Verify quality gate fails when pass rate falls below minimum."""
        gate = EvaluationQualityGate(config=EvaluationGateConfig(minimum_pass_rate=0.90))
        result = gate.evaluate_report(self.sample_report, expected_failed_ids=["case_bad_1", "case_bad_2"])
        self.assertFalse(result.passed)
        self.assertTrue(any("pass rate" in f for f in result.failures))

    def test_04_quality_gate_fails_critical_metric_below_minimum(self):
        """Verify quality gate fails when a specific critical metric is below minimum."""
        gate = EvaluationQualityGate(
            config=EvaluationGateConfig(minimum_metric_scores={"citation_validity_rate": 0.95})
        )
        result = gate.evaluate_report(self.sample_report, expected_failed_ids=["case_bad_1", "case_bad_2"])
        self.assertFalse(result.passed)
        self.assertTrue(any("citation_validity_rate" in f for f in result.failures))

    def test_05_quality_gate_regression_detection_within_tolerance(self):
        """Verify quality gate passes with a warning when score drop is within allowable tolerance."""
        baseline = {"average_overall_score": 0.90}  # Drop of 0.02, tolerance is 0.05
        gate = EvaluationQualityGate(
            config=EvaluationGateConfig(maximum_regression_delta=0.05),
            baseline_data=baseline,
        )
        result = gate.evaluate_report(self.sample_report, expected_failed_ids=["case_bad_1", "case_bad_2"])
        self.assertTrue(result.passed)
        self.assertEqual(len(result.warnings), 1)
        self.assertAlmostEqual(result.score_delta, -0.02, places=3)

    def test_06_quality_gate_regression_detection_beyond_tolerance(self):
        """Verify quality gate fails when score drop exceeds allowable tolerance."""
        baseline = {"average_overall_score": 0.98}  # Drop of 0.10, tolerance is 0.05
        gate = EvaluationQualityGate(
            config=EvaluationGateConfig(maximum_regression_delta=0.05),
            baseline_data=baseline,
        )
        result = gate.evaluate_report(self.sample_report, expected_failed_ids=["case_bad_1", "case_bad_2"])
        self.assertFalse(result.passed)
        self.assertTrue(any("Quality regression detected" in f for f in result.failures))

    def test_07_quality_gate_unexpected_failing_case_detection(self):
        """Verify quality gate detects unexpected failure not in the expected failures list."""
        gate = EvaluationQualityGate(config=EvaluationGateConfig(fail_on_unexpected_failures=True))
        # Expected only case_bad_1, but report also has case_bad_2
        result = gate.evaluate_report(self.sample_report, expected_failed_ids=["case_bad_1"])
        self.assertFalse(result.passed)
        self.assertTrue(any("Unexpected benchmark failures detected" in f for f in result.failures))
        self.assertIn("case_bad_2", str(result.failures))

    def test_08_benchmark_cli_invocation_success(self):
        """Verify run_benchmark_cli executes golden dataset and returns 0 exit code."""
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = run_benchmark_cli([])
            output = fake_out.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("LECTUREAI GENERATION EVALUATION BENCHMARK SCORECARD", output)
            self.assertIn("[GATE PASS]", output)

    def test_09_benchmark_cli_json_output(self):
        """Verify run_benchmark_cli with --json outputs valid parseable JSON."""
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = run_benchmark_cli(["--json"])
            output = fake_out.getvalue()
            self.assertEqual(exit_code, 0)
            parsed = json.loads(output)
            self.assertEqual(parsed["total_cases"], 12)
            self.assertTrue(parsed["gate_passed"])
            self.assertIn("average_overall_score", parsed)

    def test_10_quality_gate_determinism(self):
        """Verify repeated evaluations of quality gate produce identical results."""
        gate = EvaluationQualityGate(baseline_data={"average_overall_score": 0.88})
        res1 = gate.evaluate_report(self.sample_report, expected_failed_ids=["case_bad_1", "case_bad_2"])
        res2 = gate.evaluate_report(self.sample_report, expected_failed_ids=["case_bad_1", "case_bad_2"])

        self.assertEqual(res1.passed, res2.passed)
        self.assertEqual(res1.failures, res2.failures)
        self.assertEqual(res1.warnings, res2.warnings)
        self.assertEqual(res1.score_delta, res2.score_delta)
        self.assertEqual(res1.current_score, res2.current_score)


if __name__ == "__main__":
    unittest.main()
