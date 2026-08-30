import argparse
import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional
from app.services.evaluation.benchmark import BenchmarkRunner
from app.services.evaluation.quality_gate import (
    EvaluationGateConfig,
    EvaluationQualityGate,
    EvaluationGateResult,
)


def load_baseline_file(filepath: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Loads baseline metrics from JSON file if available."""
    if filepath and os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    # Fallback to default fixtures path
    default_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "tests",
        "fixtures",
        "evaluation",
        "golden_baseline.json",
    )
    if os.path.exists(default_path):
        try:
            with open(default_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


async def execute_benchmark(
    baseline_path: Optional[str] = None,
    custom_cases: Optional[List[Any]] = None,
) -> tuple[Any, EvaluationGateResult]:
    """Executes the golden benchmark and evaluates the quality gate."""
    if custom_cases is not None:
        cases = custom_cases
    else:
        from tests.fixtures.evaluation.golden_dataset import get_golden_dataset
        cases = get_golden_dataset()

    runner = BenchmarkRunner()
    report = await runner.run(cases)

    baseline_data = load_baseline_file(baseline_path)
    expected_failures = None
    if baseline_data and "failed_case_ids" in baseline_data:
        expected_failures = baseline_data["failed_case_ids"]

    gate = EvaluationQualityGate(baseline_data=baseline_data)
    gate_result = gate.evaluate_report(report, expected_failed_ids=expected_failures)

    return report, gate_result


def format_human_report(report: Any, gate_result: EvaluationGateResult) -> str:
    """Formats a human-readable console report."""
    lines = [
        "=" * 70,
        "          LECTUREAI GENERATION EVALUATION BENCHMARK SCORECARD",
        "=" * 70,
        f"Total Test Cases:       {report.total_cases}",
        f"Passed Cases:           {report.passed_cases} ({report.pass_rate * 100:.1f}%)",
        f"Failed Cases:           {report.failed_cases}",
        f"Average Overall Score:  {report.average_overall_score:.4f}",
        f"Execution Duration:     {report.duration_ms:.2f} ms",
        "-" * 70,
        "VERDICT DISTRIBUTION:",
    ]
    for verdict, count in report.verdict_counts.items():
        lines.append(f"  - {verdict:<10}: {count}")

    lines.append("-" * 70)
    lines.append("MODE-LEVEL QUALITY SCORES:")
    for mode, score in report.mode_scores.items():
        lines.append(f"  - {mode:<15}: {score:.4f}")

    lines.append("-" * 70)
    lines.append("METRIC AGGREGATES:")
    for metric, score in report.metric_aggregates.items():
        lines.append(f"  - {metric:<40}: {score:.4f}")

    if report.failed_case_ids:
        lines.append("-" * 70)
        lines.append("RECORDED FAILING FIXTURES:")
        for cid in report.failed_case_ids:
            lines.append(f"  - [FAIL] {cid}")

    lines.append("=" * 70)
    lines.append("QUALITY GATE VERDICT:")
    if gate_result.passed:
        lines.append("  >>> [GATE PASS] All release quality criteria and baselines met. <<<")
    else:
        lines.append("  >>> [GATE FAIL] Release quality criteria violated. <<<")
        for f in gate_result.failures:
            lines.append(f"      * FAILURE: {f}")

    if gate_result.warnings:
        for w in gate_result.warnings:
            lines.append(f"      * WARNING: {w}")

    if gate_result.baseline_score is not None:
        lines.append(f"Baseline Score: {gate_result.baseline_score:.4f} | Current: {gate_result.current_score:.4f} | Delta: {gate_result.score_delta:+.4f}")

    lines.append("=" * 70)
    return "\n".join(lines)


def run_benchmark_cli(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint for running benchmark quality gate."""
    parser = argparse.ArgumentParser(description="LectureAI Generation Evaluation Benchmark CLI")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON format")
    parser.add_argument("--baseline", type=str, default=None, help="Path to golden baseline JSON file")

    parsed_args = parser.parse_args(args)

    report, gate_result = asyncio.run(execute_benchmark(baseline_path=parsed_args.baseline))

    if parsed_args.json:
        output_dict = {
            "total_cases": report.total_cases,
            "passed_cases": report.passed_cases,
            "failed_cases": report.failed_cases,
            "pass_rate": report.pass_rate,
            "average_overall_score": report.average_overall_score,
            "verdict_counts": report.verdict_counts,
            "mode_scores": report.mode_scores,
            "metric_aggregates": report.metric_aggregates,
            "failed_case_ids": report.failed_case_ids,
            "gate_passed": gate_result.passed,
            "gate_failures": gate_result.failures,
            "gate_warnings": gate_result.warnings,
            "baseline_score": gate_result.baseline_score,
            "score_delta": gate_result.score_delta,
        }
        print(json.dumps(output_dict, indent=2))
    else:
        print(format_human_report(report, gate_result))

    return 0 if gate_result.passed else 1


if __name__ == "__main__":
    sys.exit(run_benchmark_cli())
