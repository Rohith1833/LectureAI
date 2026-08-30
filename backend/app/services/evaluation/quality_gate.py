from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.services.evaluation.benchmark import BenchmarkReport


class EvaluationGateConfig(BaseModel):
    """Configuration parameters and tolerances enforced by the EvaluationQualityGate."""
    minimum_overall_score: float = Field(default=0.50, description="Minimum acceptable average benchmark score")
    minimum_pass_rate: float = Field(default=0.50, description="Minimum acceptable case pass rate")
    minimum_metric_scores: Dict[str, float] = Field(
        default_factory=lambda: {
            "schema_compliance_score": 0.50,
            "citation_validity_rate": 0.50,
            "empty_abstention_accuracy": 0.50,
        },
        description="Minimum acceptable average score per named metric",
    )
    maximum_regression_delta: float = Field(
        default=0.05,
        description="Maximum allowable score decrease (0.05 = 5%) compared to expected baseline",
    )
    fail_on_evaluation_errors: bool = Field(
        default=True,
        description="Fail gate if any evaluator threw an unhandled execution exception",
    )
    fail_on_unexpected_failures: bool = Field(
        default=True,
        description="Fail gate if actual failed case IDs differ from expected failing fixtures",
    )


class EvaluationGateResult(BaseModel):
    """Decision and diagnostic summary produced by the EvaluationQualityGate."""
    passed: bool
    failures: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    baseline_score: Optional[float] = None
    current_score: float
    score_delta: Optional[float] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class EvaluationQualityGate:
    """
    Evaluates a BenchmarkReport against defined quality thresholds and historical
    version-controlled baselines to produce an authoritative CI release verdict.
    """

    def __init__(
        self,
        config: Optional[EvaluationGateConfig] = None,
        baseline_data: Optional[Dict[str, Any]] = None,
    ):
        self.config = config or EvaluationGateConfig()
        self.baseline_data = baseline_data

    def evaluate_report(
        self,
        report: BenchmarkReport,
        expected_failed_ids: Optional[List[str]] = None,
    ) -> EvaluationGateResult:
        failures: List[str] = []
        warnings: List[str] = []

        # 1. Overall Score Check
        if report.average_overall_score < self.config.minimum_overall_score:
            failures.append(
                f"Overall benchmark score {report.average_overall_score:.4f} is below "
                f"minimum threshold {self.config.minimum_overall_score:.4f}."
            )

        # 2. Pass Rate Check
        if report.pass_rate < self.config.minimum_pass_rate:
            failures.append(
                f"Benchmark pass rate {report.pass_rate:.4f} is below "
                f"minimum threshold {self.config.minimum_pass_rate:.4f}."
            )

        # 3. Critical Metric Scores Check
        for metric_name, min_score in self.config.minimum_metric_scores.items():
            actual_score = report.metric_aggregates.get(metric_name)
            if actual_score is not None and actual_score < min_score:
                failures.append(
                    f"Metric '{metric_name}' average score {actual_score:.4f} is below "
                    f"minimum threshold {min_score:.4f}."
                )

        # 4. Unexpected Failures Check
        if self.config.fail_on_unexpected_failures and expected_failed_ids is not None:
            actual_failures = set(report.failed_case_ids)
            expected_failures = set(expected_failed_ids)

            unforeseen_failures = actual_failures - expected_failures
            if unforeseen_failures:
                failures.append(
                    f"Unexpected benchmark failures detected: {sorted(list(unforeseen_failures))}"
                )

            unforeseen_passes = expected_failures - actual_failures
            if unforeseen_passes:
                warnings.append(
                    f"Cases expected to fail passed: {sorted(list(unforeseen_passes))}"
                )

        # 5. Baseline Regression Comparison Check
        baseline_score = None
        score_delta = None

        if self.baseline_data and "average_overall_score" in self.baseline_data:
            baseline_score = float(self.baseline_data["average_overall_score"])
            score_delta = round(report.average_overall_score - baseline_score, 4)

            if score_delta < -self.config.maximum_regression_delta:
                failures.append(
                    f"Quality regression detected: current score {report.average_overall_score:.4f} "
                    f"is {abs(score_delta):.4f} lower than baseline {baseline_score:.4f} "
                    f"(allowed delta: {self.config.maximum_regression_delta:.4f})."
                )
            elif score_delta < 0:
                warnings.append(
                    f"Minor quality decrease within allowable tolerance: {score_delta:.4f}"
                )

        passed = len(failures) == 0

        return EvaluationGateResult(
            passed=passed,
            failures=failures,
            warnings=warnings,
            baseline_score=baseline_score,
            current_score=report.average_overall_score,
            score_delta=score_delta,
            details={
                "total_cases": report.total_cases,
                "passed_cases": report.passed_cases,
                "failed_cases": report.failed_cases,
                "pass_rate": report.pass_rate,
                "verdict_counts": report.verdict_counts,
            },
        )
