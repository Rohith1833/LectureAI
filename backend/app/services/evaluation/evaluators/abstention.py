from typing import List
from app.schemas.evaluation import EvaluationRequest, MetricScore
from app.schemas.generation import GroundingStatus
from app.services.evaluation.base import BaseEvaluator


class AbstentionEvaluator(BaseEvaluator):
    """
    Deterministically evaluates whether the model properly abstains when context is
    empty or insufficient, rather than fabricating ungrounded content.
    """

    @property
    def name(self) -> str:
        return "abstention"

    async def evaluate(self, request: EvaluationRequest) -> List[MetricScore]:
        result = request.generation_result
        context_sources = request.context_sources or {}
        has_context = len(context_sources) > 0

        is_insufficient_status = result.overall_grounding_status == GroundingStatus.INSUFFICIENT_CONTEXT
        contains_insufficient_marker = (
            "INSUFFICIENT_CONTEXT" in (result.answer or "")
            or any("INSUFFICIENT_CONTEXT" in getattr(c, "text", "") for c in (result.claims or []))
        )
        abstained = is_insufficient_status or contains_insufficient_marker

        if not has_context:
            if abstained:
                score = 1.0
                passed = True
                reason = "Model correctly abstained given empty context."
            elif (result.claims and len(result.claims) > 0) or (result.answer and len(result.answer.strip()) > 30):
                score = 0.0
                passed = False
                reason = "Model generated substantive ungrounded response despite empty context."
            else:
                score = 1.0
                passed = True
                reason = "Empty context handled with minimal non-substantive output."
        else:
            # When context was provided, both grounded generation and explicit query-abstention are valid
            if abstained:
                score = 1.0
                passed = True
                reason = "Model accurately abstained because supplied context did not contain answer to prompt."
            else:
                score = 1.0
                passed = True
                reason = "Generation proceeded normally with supplied context."

        return [
            MetricScore(
                name="empty_abstention_accuracy",
                score=score,
                threshold=1.0,
                passed=passed,
                weight=2.0,
                reason=reason,
                metadata={
                    "has_context": has_context,
                    "abstained": abstained,
                    "grounding_status": result.overall_grounding_status.value if result.overall_grounding_status else None,
                },
            )
        ]
