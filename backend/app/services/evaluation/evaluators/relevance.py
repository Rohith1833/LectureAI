import re
from typing import Any, Dict, List, Set
from app.schemas.evaluation import EvaluationRequest, MetricScore
from app.schemas.generation import GenerationMode, GroundingStatus
from app.services.evaluation.base import BaseEvaluator
from app.services.evaluation.evaluators.faithfulness import (
    STOP_WORDS,
    tokenize_preserving_technical,
)


def extract_all_result_text(result_dict: Dict[str, Any], answer: str, mode: GenerationMode) -> str:
    """Extracts all text content across answer and structured output fields."""
    parts = [answer or ""]

    struct = result_dict.get("structured_output")
    if isinstance(struct, dict):
        if struct.get("title"):
            parts.append(str(struct["title"]))

        # Comparison fields
        for s in struct.get("subjects", []):
            parts.append(str(s))
        for row in struct.get("comparison_table", []):
            if isinstance(row, dict):
                parts.append(str(row.get("dimension", "")))
                parts.append(str(row.get("explanation", "")))
                for v in row.get("values", []):
                    if isinstance(v, dict):
                        parts.append(str(v.get("value", "")))
        for sim in struct.get("similarities", []):
            if isinstance(sim, dict):
                parts.append(str(sim.get("text", "")))
        for diff in struct.get("differences", []):
            if isinstance(diff, dict):
                parts.append(str(diff.get("text", "")))

        # Study Guide fields
        for kc in struct.get("key_concepts", []):
            if isinstance(kc, dict):
                parts.append(str(kc.get("concept", "")))
                parts.append(str(kc.get("definition", "")))
        for obj in struct.get("learning_objectives", []):
            parts.append(str(obj))
        for rq in struct.get("review_questions", []):
            if isinstance(rq, dict):
                parts.append(str(rq.get("question", "")))
                parts.append(str(rq.get("answer", "")))
                parts.append(str(rq.get("explanation", "")))

    return " ".join(parts)


class RelevanceEvaluator(BaseEvaluator):
    """
    Deterministically evaluates whether the generated output directly addresses the
    user's query, requested subjects, and scope parameters.
    """

    @property
    def name(self) -> str:
        return "relevance"

    async def evaluate(self, request: EvaluationRequest) -> List[MetricScore]:
        gen_req = request.generation_request
        gen_res = request.generation_result
        mode = gen_req.mode or gen_res.mode

        # 1. Check for valid abstention
        if (
            gen_res.overall_grounding_status == GroundingStatus.INSUFFICIENT_CONTEXT
            or "INSUFFICIENT_CONTEXT" in (gen_res.answer or "")
        ):
            return [
                MetricScore(
                    name="answer_relevance_score",
                    score=1.0,
                    threshold=0.70,
                    passed=True,
                    weight=1.5,
                    reason="Model appropriately signaled insufficient context in response to query.",
                    metadata={"abstained": True},
                )
            ]

        # 2. Extract query keywords
        raw_query = gen_req.query or ""
        query_tokens = tokenize_preserving_technical(raw_query)

        # Mode-specific enrichment: include explicit comparison subjects
        if mode == GenerationMode.COMPARISON and gen_req.comparison_options:
            for sub in gen_req.comparison_options.subjects:
                query_tokens.extend(tokenize_preserving_technical(sub))

        unique_query_tokens = []
        for t in query_tokens:
            if t not in unique_query_tokens:
                unique_query_tokens.append(t)

        if not unique_query_tokens:
            return [
                MetricScore(
                    name="answer_relevance_score",
                    score=1.0,
                    threshold=0.70,
                    passed=True,
                    weight=1.5,
                    reason="Empty or non-substantive query tokens; neutral score.",
                    metadata={"query_tokens_count": 0},
                )
            ]

        # 3. Gather output tokens across text & structured elements
        result_dict = gen_res.model_dump()
        all_output_text = extract_all_result_text(result_dict, gen_res.answer, mode)
        output_tokens = set(tokenize_preserving_technical(all_output_text))

        # 4. Calculate Keyword Recall on Query
        matched_tokens = [t for t in unique_query_tokens if t in output_tokens]
        keyword_recall = len(matched_tokens) / len(unique_query_tokens)
        relevance_score = round(keyword_recall, 4)

        # For comparison mode, ensure all requested comparison subjects are mentioned
        if mode == GenerationMode.COMPARISON and gen_req.comparison_options:
            subjects = gen_req.comparison_options.subjects
            output_lower = all_output_text.lower()
            missing_subjects = [s for s in subjects if s.lower() not in output_lower]
            if missing_subjects:
                relevance_score = round(relevance_score * 0.7, 4)

        relevance_score = min(1.0, max(0.0, relevance_score))
        is_passed = relevance_score >= 0.70

        reason_str = (
            f"Relevance score {relevance_score:.2f}: {len(matched_tokens)}/{len(unique_query_tokens)} "
            f"query terms matched in generated response."
        )

        return [
            MetricScore(
                name="answer_relevance_score",
                score=relevance_score,
                threshold=0.70,
                passed=is_passed,
                weight=1.5,
                reason=reason_str,
                metadata={
                    "query_terms_count": len(unique_query_tokens),
                    "matched_terms_count": len(matched_tokens),
                    "matched_terms": matched_tokens,
                    "mode": mode.value,
                },
            )
        ]
