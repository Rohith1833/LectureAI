import time
from typing import Dict, List, Optional
from loguru import logger
from app.schemas.evaluation import (
    EvaluationRequest,
    EvaluationResult,
    EvaluationVerdict,
    MetricScore,
)
from app.services.evaluation.base import BaseEvaluator


class EvaluationEngine:
    """
    Orchestrates generation quality assessment across registered evaluators.
    Aggregates individual metric scores, calculates weighted composite metrics,
    and produces standardized EvaluationResult records.
    """

    def __init__(self, evaluators: Optional[List[BaseEvaluator]] = None):
        self._evaluators: Dict[str, BaseEvaluator] = {}
        if evaluators:
            for ev in evaluators:
                self.register_evaluator(ev)

    def register_evaluator(self, evaluator: BaseEvaluator) -> None:
        """Registers a new evaluator component."""
        name = evaluator.name
        if name in self._evaluators:
            logger.warning(f"Overwriting existing evaluator '{name}' in EvaluationEngine")
        self._evaluators[name] = evaluator
        logger.debug(f"Registered evaluator '{name}' in EvaluationEngine")

    def unregister_evaluator(self, name: str) -> None:
        """Removes an evaluator by name if present."""
        if name in self._evaluators:
            del self._evaluators[name]
            logger.debug(f"Unregistered evaluator '{name}' from EvaluationEngine")

    @property
    def evaluators(self) -> List[BaseEvaluator]:
        """Returns list of currently active evaluators."""
        return list(self._evaluators.values())

    async def evaluate(self, request: EvaluationRequest) -> EvaluationResult:
        """
        Executes evaluation across all registered evaluators for the given request.

        Args:
            request: EvaluationRequest containing input, output, and context.

        Returns:
            EvaluationResult detailing metric scores, composite score, and verdict.
        """
        start_time = time.perf_counter()
        collected_metrics: List[MetricScore] = []
        evaluator_diagnostics: Dict[str, Any] = {}

        for name, evaluator in self._evaluators.items():
            try:
                ev_start = time.perf_counter()
                scores = await evaluator.evaluate(request)
                ev_duration_ms = (time.perf_counter() - ev_start) * 1000.0
                collected_metrics.extend(scores)
                evaluator_diagnostics[name] = {
                    "status": "SUCCESS",
                    "metrics_count": len(scores),
                    "duration_ms": round(ev_duration_ms, 2),
                }
            except Exception as e:
                logger.error(f"Evaluator '{name}' failed during execution: {e}")
                evaluator_diagnostics[name] = {
                    "status": "ERROR",
                    "error": str(e),
                }

        # Calculate composite weighted score
        total_weight = sum(m.weight for m in collected_metrics)
        if total_weight > 0.0:
            weighted_sum = sum(m.score * m.weight for m in collected_metrics)
            overall_score = round(weighted_sum / total_weight, 4)
        else:
            overall_score = 1.0

        # Determine overall pass / fail
        overall_passed = all(m.passed for m in collected_metrics) if collected_metrics else True

        # Determine categorical verdict
        if not overall_passed or overall_score < 0.60:
            verdict = EvaluationVerdict.FAIL
        elif overall_score < 0.85:
            verdict = EvaluationVerdict.WARNING
        else:
            verdict = EvaluationVerdict.PASS

        total_duration_ms = (time.perf_counter() - start_time) * 1000.0

        diagnostics = {
            "total_evaluators": len(self._evaluators),
            "total_metrics": len(collected_metrics),
            "failed_metrics": [m.name for m in collected_metrics if not m.passed],
            "total_duration_ms": round(total_duration_ms, 2),
            "evaluator_runs": evaluator_diagnostics,
        }

        return EvaluationResult(
            mode=request.generation_request.mode or request.generation_result.mode,
            overall_passed=overall_passed,
            overall_score=overall_score,
            verdict=verdict,
            metrics=collected_metrics,
            diagnostics=diagnostics,
        )
