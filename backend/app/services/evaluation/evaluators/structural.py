from typing import Any, Dict, List
from app.schemas.evaluation import EvaluationRequest, MetricScore
from app.schemas.generation import GenerationMode
from app.services.evaluation.base import BaseEvaluator


class StructuralEvaluator(BaseEvaluator):
    """
    Deterministically evaluates the structural schema compliance of a GenerationResult.
    Validates common core fields and mode-specific structured schemas (Comparison, Study Guide).
    """

    @property
    def name(self) -> str:
        return "structural"

    async def evaluate(self, request: EvaluationRequest) -> List[MetricScore]:
        result = request.generation_result
        mode = request.generation_request.mode or result.mode
        reasons: List[str] = []

        # 1. Common Core Validation
        if not result.mode:
            reasons.append("Missing 'mode' field in GenerationResult.")
        elif result.mode != mode:
            reasons.append(f"Result mode '{result.mode}' does not match requested mode '{mode}'.")

        if result.overall_grounding_status is None:
            reasons.append("Missing 'overall_grounding_status' in GenerationResult.")

        if not isinstance(result.claims, list):
            reasons.append("'claims' must be a list in GenerationResult.")

        if not isinstance(result.citations, dict):
            reasons.append("'citations' must be a dictionary in GenerationResult.")

        # 2. Mode-Specific Structural Checks
        if mode in (GenerationMode.QA, GenerationMode.EXPLANATION, GenerationMode.SUMMARY):
            if not isinstance(result.answer, str) or not result.answer.strip():
                reasons.append(f"Mode {mode.value} requires a non-empty string in 'answer'.")

        elif mode == GenerationMode.COMPARISON:
            struct = result.structured_output
            if not isinstance(struct, dict) or not struct:
                reasons.append("Mode COMPARISON requires a non-empty 'structured_output' dictionary.")
            else:
                # Validate Comparison fields
                if not isinstance(struct.get("title"), str) or not struct["title"].strip():
                    reasons.append("Comparison 'structured_output' requires a non-empty 'title'.")

                subjects = struct.get("subjects")
                if not isinstance(subjects, list) or len(subjects) < 2:
                    reasons.append("Comparison 'structured_output' requires 'subjects' list with at least 2 items.")

                table = struct.get("comparison_table")
                if not isinstance(table, list) or len(table) == 0:
                    reasons.append("Comparison 'structured_output' requires a non-empty 'comparison_table' list.")
                else:
                    for row_idx, row in enumerate(table):
                        if not isinstance(row, dict) or not row.get("dimension"):
                            reasons.append(f"Comparison table row {row_idx} missing 'dimension' string.")
                        if not isinstance(row.get("values"), list) or len(row["values"]) == 0:
                            reasons.append(f"Comparison table row {row_idx} missing 'values' list.")

                if not isinstance(struct.get("similarities"), list):
                    reasons.append("Comparison 'structured_output' requires 'similarities' list.")

                if not isinstance(struct.get("differences"), list):
                    reasons.append("Comparison 'structured_output' requires 'differences' list.")

        elif mode == GenerationMode.STUDY_GUIDE:
            struct = result.structured_output
            if not isinstance(struct, dict) or not struct:
                reasons.append("Mode STUDY_GUIDE requires a non-empty 'structured_output' dictionary.")
            else:
                # Validate Study Guide fields
                if not isinstance(struct.get("title"), str) or not struct["title"].strip():
                    reasons.append("Study Guide 'structured_output' requires a non-empty 'title'.")

                if not isinstance(struct.get("answer"), str) and not (isinstance(result.answer, str) and result.answer.strip()):
                    reasons.append("Study Guide requires a non-empty overview string in 'answer'.")

                if not isinstance(struct.get("key_concepts"), list):
                    reasons.append("Study Guide 'structured_output' requires 'key_concepts' list.")

                if not isinstance(struct.get("learning_objectives"), list):
                    reasons.append("Study Guide 'structured_output' requires 'learning_objectives' list.")

                questions = struct.get("review_questions")
                if not isinstance(questions, list) or len(questions) == 0:
                    reasons.append("Study Guide 'structured_output' requires a non-empty 'review_questions' list.")
                else:
                    for q_idx, q in enumerate(questions):
                        if not isinstance(q, dict) or not q.get("question") or not q.get("answer"):
                            reasons.append(f"Study Guide review question {q_idx} missing 'question' or 'answer'.")

        is_passed = len(reasons) == 0
        score = 1.0 if is_passed else 0.0
        reason_str = "All structural schema constraints verified." if is_passed else "; ".join(reasons)

        return [
            MetricScore(
                name="schema_compliance_score",
                score=score,
                threshold=1.0,
                passed=is_passed,
                weight=3.0,
                reason=reason_str,
                metadata={"mode": mode.value, "error_count": len(reasons)},
            )
        ]
