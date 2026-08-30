from typing import Any, Dict, List, Set
from app.schemas.evaluation import EvaluationRequest, MetricScore
from app.schemas.generation import GenerationMode
from app.services.evaluation.base import BaseEvaluator


class StudyGuideEvaluator(BaseEvaluator):
    """
    Deterministically evaluates mode-specific quality dimensions for STUDY_GUIDE generation:
    - Pedagogical content completeness across key concepts, objectives, and overview
    - Review question count fidelity and question deduplication
    """

    @property
    def name(self) -> str:
        return "study_guide"

    async def evaluate(self, request: EvaluationRequest) -> List[MetricScore]:
        result = request.generation_result
        mode = request.generation_request.mode or result.mode

        # Mode isolation: only evaluate for STUDY_GUIDE mode
        if mode != GenerationMode.STUDY_GUIDE:
            return []

        gen_req = request.generation_request
        struct = result.structured_output or {}

        # 1. Content Coverage (Concepts, Objectives, Overview)
        key_concepts = struct.get("key_concepts", [])
        objectives = struct.get("learning_objectives", [])
        overview = struct.get("answer") or result.answer or ""

        # Key concepts score
        valid_concepts = 0
        if isinstance(key_concepts, list) and len(key_concepts) > 0:
            for kc in key_concepts:
                if isinstance(kc, dict) and kc.get("concept") and kc.get("definition"):
                    valid_concepts += 1
            concepts_score = 1.0 if valid_concepts >= 1 else 0.0
        else:
            concepts_score = 0.0

        # Learning objectives score
        valid_objectives = 0
        if isinstance(objectives, list) and len(objectives) > 0:
            for obj in objectives:
                if isinstance(obj, str) and obj.strip():
                    valid_objectives += 1
            objectives_score = 1.0 if valid_objectives >= 1 else 0.0
        else:
            objectives_score = 0.0

        # Overview score
        overview_score = 1.0 if isinstance(overview, str) and len(overview.strip()) > 10 else 0.0

        content_score = round((concepts_score + objectives_score + overview_score) / 3.0, 4)
        content_reason = (
            f"Content completeness {content_score:.2f}: {valid_concepts} valid concepts, "
            f"{valid_objectives} objectives, overview present: {bool(overview_score)}."
        )

        content_metric = MetricScore(
            name="study_guide_content_coverage",
            score=content_score,
            threshold=0.80,
            passed=content_score >= 0.80,
            weight=2.0,
            reason=content_reason,
            metadata={
                "valid_concepts_count": valid_concepts,
                "valid_objectives_count": valid_objectives,
                "has_overview": bool(overview_score),
            },
        )

        # 2. Review Question Coverage & Deduplication
        requested_count = 5
        if gen_req.study_options and gen_req.study_options.question_count:
            requested_count = gen_req.study_options.question_count

        questions = struct.get("review_questions", [])
        valid_questions: List[Dict[str, Any]] = []
        seen_question_texts: Set[str] = set()
        duplicate_count = 0

        if isinstance(questions, list):
            for q in questions:
                if isinstance(q, dict) and q.get("question") and q.get("answer"):
                    q_text = str(q["question"]).strip().lower()
                    if q_text in seen_question_texts:
                        duplicate_count += 1
                    else:
                        seen_question_texts.add(q_text)
                        valid_questions.append(q)

        unique_valid_count = len(valid_questions)
        question_score = round(min(1.0, unique_valid_count / max(1, requested_count)), 4)

        if duplicate_count > 0:
            question_reason = (
                f"Generated {unique_valid_count}/{requested_count} unique valid questions "
                f"({duplicate_count} duplicates detected)."
            )
        else:
            question_reason = f"Generated {unique_valid_count}/{requested_count} unique valid review questions."

        question_metric = MetricScore(
            name="study_guide_question_coverage",
            score=question_score,
            threshold=0.80,
            passed=question_score >= 0.80,
            weight=2.0,
            reason=question_reason,
            metadata={
                "requested_questions": requested_count,
                "unique_valid_questions": unique_valid_count,
                "duplicate_questions": duplicate_count,
            },
        )

        return [content_metric, question_metric]
