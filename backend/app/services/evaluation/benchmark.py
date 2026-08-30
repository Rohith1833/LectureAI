import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.schemas.evaluation import (
    EvaluationRequest,
    EvaluationResult,
    EvaluationVerdict,
)
from app.schemas.generation import GenerationMode, GenerationRequest, GenerationResult
from app.services.evaluation.engine import EvaluationEngine


class EvaluationCase(BaseModel):
    """Encapsulates a single benchmark test case with input, output, and context."""
    id: str = Field(..., description="Unique test case identifier")
    description: str = Field(..., description="Human-readable description of test case intent")
    generation_request: GenerationRequest = Field(..., description="Original generation request envelope")
    generation_result: GenerationResult = Field(..., description="Generation result under benchmark evaluation")
    context_sources: Dict[str, Any] = Field(default_factory=dict, description="Supplied canonical context sources")
    expected_verdict: Optional[EvaluationVerdict] = Field(default=None, description="Optional expected evaluation verdict")
    tags: List[str] = Field(default_factory=list, description="Categorical tags for filtering (e.g. ['grounded', 'qa'])")


class BenchmarkReport(BaseModel):
    """Aggregate quality scorecard produced by the BenchmarkRunner across evaluation cases."""
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    average_overall_score: float
    verdict_counts: Dict[str, int]
    metric_aggregates: Dict[str, float]
    mode_scores: Dict[str, float]
    failed_case_ids: List[str]
    case_results: List[Dict[str, Any]]
    duration_ms: float


class BenchmarkRunner:
    """
    Executes a deterministic collection of EvaluationCase fixtures against the
    EvaluationEngine, producing aggregate quality benchmarks and regression scorecards.
    """

    def __init__(self, engine: Optional[EvaluationEngine] = None):
        if engine is None:
            from app.services.evaluation import create_default_evaluation_engine
            self._engine = create_default_evaluation_engine()
        else:
            self._engine = engine

    async def run(self, cases: List[EvaluationCase]) -> BenchmarkReport:
        start_time = time.perf_counter()

        if not cases:
            return BenchmarkReport(
                total_cases=0,
                passed_cases=0,
                failed_cases=0,
                pass_rate=1.0,
                average_overall_score=1.0,
                verdict_counts={"PASS": 0, "WARNING": 0, "FAIL": 0},
                metric_aggregates={},
                mode_scores={},
                failed_case_ids=[],
                case_results=[],
                duration_ms=0.0,
            )

        case_results: List[Dict[str, Any]] = []
        passed_cases = 0
        failed_case_ids: List[str] = []
        verdict_counts = {"PASS": 0, "WARNING": 0, "FAIL": 0}
        metric_sums: Dict[str, float] = {}
        metric_counts: Dict[str, int] = {}
        mode_sums: Dict[str, float] = {}
        mode_counts: Dict[str, int] = {}

        for case in cases:
            eval_req = EvaluationRequest(
                generation_request=case.generation_request,
                generation_result=case.generation_result,
                context_sources=case.context_sources,
            )

            res = await self._engine.evaluate(eval_req)

            # Record pass / fail
            if res.overall_passed:
                passed_cases += 1
            else:
                failed_case_ids.append(case.id)

            # Record verdict counts
            v_key = res.verdict.value if hasattr(res.verdict, "value") else str(res.verdict)
            verdict_counts[v_key] = verdict_counts.get(v_key, 0) + 1

            # Mode scores
            m_key = res.mode.value if hasattr(res.mode, "value") else str(res.mode)
            mode_sums[m_key] = mode_sums.get(m_key, 0.0) + res.overall_score
            mode_counts[m_key] = mode_counts.get(m_key, 0) + 1

            # Metric aggregates
            for m in res.metrics:
                metric_sums[m.name] = metric_sums.get(m.name, 0.0) + m.score
                metric_counts[m.name] = metric_counts.get(m.name, 0) + 1

            case_results.append({
                "id": case.id,
                "description": case.description,
                "mode": m_key,
                "overall_score": res.overall_score,
                "overall_passed": res.overall_passed,
                "verdict": v_key,
                "metrics_count": len(res.metrics),
            })

        duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        total_cases = len(cases)
        failed_cases = total_cases - passed_cases
        pass_rate = round(passed_cases / total_cases, 4) if total_cases > 0 else 1.0

        all_scores = [c["overall_score"] for c in case_results]
        avg_score = round(sum(all_scores) / total_cases, 4) if total_cases > 0 else 1.0

        metric_aggregates = {
            m_name: round(metric_sums[m_name] / metric_counts[m_name], 4)
            for m_name in metric_sums
        }

        mode_scores = {
            m_mode: round(mode_sums[m_mode] / mode_counts[m_mode], 4)
            for m_mode in mode_sums
        }

        return BenchmarkReport(
            total_cases=total_cases,
            passed_cases=passed_cases,
            failed_cases=failed_cases,
            pass_rate=pass_rate,
            average_overall_score=avg_score,
            verdict_counts=verdict_counts,
            metric_aggregates=metric_aggregates,
            mode_scores=mode_scores,
            failed_case_ids=failed_case_ids,
            case_results=case_results,
            duration_ms=duration_ms,
        )
