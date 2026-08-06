from typing import Dict, List, Any
from app.services.intelligence.context import IntelligenceContext
from app.services.intelligence.annotations import QualityAnnotation, HierarchyAnnotation
from app.services.intelligence.quality.evaluators.base import BaseQualityEvaluator


class HierarchyQualityEvaluator(BaseQualityEvaluator):
    """Evaluates tree construction integrity, logical nesting depth consistency, and orphan counts."""

    @property
    def name(self) -> str:
        return "hierarchy_quality"

    def evaluate(self, context: IntelligenceContext) -> Dict[str, Any]:
        doc = context.document
        warnings: List[Dict[str, Any]] = []
        recommendations: List[Dict[str, Any]] = []

        if not doc or not doc.blocks:
            return {"score": 1.0, "warnings": [], "recommendations": []}

        # Query validation QualityAnnotation written by validator module
        q_annos = context.annotation_store.find_by_type(QualityAnnotation)
        validation_anno = next((q for q in q_annos if q.provenance == "HIERARCHY_VALIDATION_MODULE"), None)

        if validation_anno:
            hierarchy_score = validation_anno.confidence.score
            orphan_count = validation_anno.metadata.get("orphan_count", 0)
            cycle_detected = validation_anno.metadata.get("cycle_detected", False)
            warning_count = validation_anno.metadata.get("warning_count", 0)
        else:
            # Fallback checks if validator did not run or was skipped
            hierarchy_score = 1.0
            orphan_count = 0
            cycle_detected = False
            warning_count = 0

            # Estimate based on parent_id presence
            has_headings = any(b.block_type == "HEADING" for b in doc.blocks)
            if has_headings:
                orphans = sum(1 for b in doc.blocks if b.parent_block_id is None and b.block_type not in ("HEADING", "HEADER", "FOOTER", "PAGE_NUMBER"))
                if orphans > 0:
                    orphan_count = orphans
                    hierarchy_score = max(0.0, 1.0 - (orphans / len(doc.blocks)))

        if cycle_detected:
            warnings.append({
                "warning_code": "CYCLIC_HIERARCHY_RELATIONS",
                "severity": "CRITICAL",
                "message": "Cycle detected involving logical hierarchy parents chain.",
                "target_id": doc.upload_id,
            })

        if orphan_count > len(doc.blocks) * 0.1:
            warnings.append({
                "warning_code": "LARGE_ORPHAN_COUNT",
                "severity": "WARNING",
                "message": f"High ratio of orphan blocks found in document: {orphan_count} blocks.",
                "target_id": doc.upload_id,
                "metadata": {"orphan_count": orphan_count}
            })

        if hierarchy_score < 0.60:
            recommendations.append({
                "recommendation_code": "MANUAL_REVIEW_REQUIRED",
                "severity": "WARNING",
                "message": "Hierarchy consistency is low. Logical structure review is required.",
                "target_id": doc.upload_id,
            })

        return {
            "score": hierarchy_score,
            "warnings": warnings,
            "recommendations": recommendations,
        }
