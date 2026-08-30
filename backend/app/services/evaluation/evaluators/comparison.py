from typing import Any, Dict, List, Set
from app.schemas.evaluation import EvaluationRequest, MetricScore
from app.schemas.generation import GenerationMode
from app.services.evaluation.base import BaseEvaluator


class ComparisonEvaluator(BaseEvaluator):
    """
    Deterministically evaluates mode-specific quality dimensions for COMPARISON generation:
    - Subject coverage across structured table and subjects list
    - Explicit dimension coverage in the comparison table
    - Completeness and balance of similarities and differences
    """

    @property
    def name(self) -> str:
        return "comparison"

    async def evaluate(self, request: EvaluationRequest) -> List[MetricScore]:
        result = request.generation_result
        mode = request.generation_request.mode or result.mode

        # Mode isolation: only evaluate for COMPARISON mode
        if mode != GenerationMode.COMPARISON:
            return []

        gen_req = request.generation_request
        struct = result.structured_output or {}

        # 1. Subject Coverage
        requested_subjects = []
        if gen_req.comparison_options and gen_req.comparison_options.subjects:
            requested_subjects = gen_req.comparison_options.subjects

        if not requested_subjects:
            subject_coverage_score = 1.0
            subject_reason = "No explicit comparison subjects requested; skipped."
        else:
            output_subjects = {s.lower().strip() for s in struct.get("subjects", []) if isinstance(s, str)}
            # Also scan table rows
            table = struct.get("comparison_table", [])
            table_subjects: Set[str] = set()
            for row in table:
                if isinstance(row, dict):
                    for v in row.get("values", []):
                        if isinstance(v, dict) and v.get("subject"):
                            table_subjects.add(v["subject"].lower().strip())

            covered_count = 0
            missing_subjects = []
            for req_sub in requested_subjects:
                sub_norm = req_sub.lower().strip()
                if sub_norm in output_subjects or sub_norm in table_subjects:
                    covered_count += 1
                else:
                    missing_subjects.append(req_sub)

            subject_coverage_score = round(covered_count / len(requested_subjects), 4)
            if missing_subjects:
                subject_reason = f"Missing requested subjects in comparison: {missing_subjects}"
            else:
                subject_reason = f"All {len(requested_subjects)} requested subjects covered in comparison."

        subject_metric = MetricScore(
            name="comparison_subject_coverage",
            score=subject_coverage_score,
            threshold=1.0,
            passed=subject_coverage_score >= 1.0,
            weight=2.0,
            reason=subject_reason,
            metadata={"requested_subjects": requested_subjects},
        )

        # 2. Dimension Coverage
        requested_dimensions = []
        if gen_req.comparison_options and gen_req.comparison_options.dimensions:
            requested_dimensions = gen_req.comparison_options.dimensions

        table = struct.get("comparison_table", [])
        if not requested_dimensions:
            dim_coverage_score = 1.0 if len(table) > 0 else 0.0
            dim_reason = "No explicit dimensions requested; generic table presence evaluated."
        else:
            table_dims = {
                row.get("dimension", "").lower().strip()
                for row in table
                if isinstance(row, dict) and row.get("dimension")
            }
            covered_dims = sum(1 for d in requested_dimensions if d.lower().strip() in table_dims)
            dim_coverage_score = round(covered_dims / len(requested_dimensions), 4)
            dim_reason = f"{covered_dims}/{len(requested_dimensions)} requested dimensions present in table."

        dim_metric = MetricScore(
            name="comparison_dimension_coverage",
            score=dim_coverage_score,
            threshold=1.0,
            passed=dim_coverage_score >= 1.0,
            weight=1.5,
            reason=dim_reason,
            metadata={"requested_dimensions": requested_dimensions},
        )

        # 3. Comparison Table Completeness
        if not table or not isinstance(table, list):
            table_completeness = 0.0
            table_reason = "Comparison table is empty or missing."
        else:
            expected_subjects_count = len(requested_subjects) if requested_subjects else 2
            total_expected_cells = len(table) * expected_subjects_count
            populated_cells = 0

            for row in table:
                if isinstance(row, dict) and row.get("dimension"):
                    values = row.get("values", [])
                    if isinstance(values, list):
                        for v in values:
                            if isinstance(v, dict) and v.get("value") and str(v["value"]).strip():
                                populated_cells += 1

            table_completeness = round(min(1.0, populated_cells / max(1, total_expected_cells)), 4)
            table_reason = f"Comparison table populated {populated_cells}/{total_expected_cells} expected cells."

        table_metric = MetricScore(
            name="comparison_table_completeness",
            score=table_completeness,
            threshold=0.80,
            passed=table_completeness >= 0.80,
            weight=1.5,
            reason=table_reason,
            metadata={"table_rows_count": len(table) if isinstance(table, list) else 0},
        )

        # 4. Similarities and Differences Balance
        similarities = struct.get("similarities", [])
        differences = struct.get("differences", [])

        has_sim = isinstance(similarities, list) and len(similarities) > 0
        has_diff = isinstance(differences, list) and len(differences) > 0

        if has_sim and has_diff:
            balance_score = 1.0
            balance_reason = f"Both similarities ({len(similarities)}) and differences ({len(differences)}) populated."
        elif has_sim or has_diff:
            balance_score = 0.5
            balance_reason = "Comparison contains only similarities or only differences, not both."
        else:
            balance_score = 0.0
            balance_reason = "Comparison contains neither similarities nor differences."

        balance_metric = MetricScore(
            name="comparison_similarity_difference_balance",
            score=balance_score,
            threshold=0.80,
            passed=balance_score >= 0.80,
            weight=1.0,
            reason=balance_reason,
            metadata={
                "similarities_count": len(similarities) if isinstance(similarities, list) else 0,
                "differences_count": len(differences) if isinstance(differences, list) else 0,
            },
        )

        return [subject_metric, dim_metric, table_metric, balance_metric]
