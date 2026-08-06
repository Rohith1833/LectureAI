from typing import Dict, List, Any
from app.services.intelligence.context import IntelligenceContext
from app.services.intelligence.annotations import SemanticAnnotation
from app.services.intelligence.quality.evaluators.base import BaseQualityEvaluator
from app.schemas.document import BlockType


class SemanticQualityEvaluator(BaseQualityEvaluator):
    """Evaluates classification accuracy, confidence distribution, and structural uncertainties."""

    @property
    def name(self) -> str:
        return "semantic_quality"

    def evaluate(self, context: IntelligenceContext) -> Dict[str, Any]:
        doc = context.document
        warnings: List[Dict[str, Any]] = []
        recommendations: List[Dict[str, Any]] = []

        if not doc or not doc.blocks:
            return {"score": 1.0, "warnings": [], "recommendations": []}

        # Fetch SemanticAnnotations
        semantic_annos = context.annotation_store.find_by_type(SemanticAnnotation)
        anno_map = {a.target_id: a for a in semantic_annos}

        total_blocks = len(doc.blocks)
        unknown_blocks_count = 0
        sum_confidence = 0.0
        low_confidence_count = 0

        for block in doc.blocks:
            # Default fallback confidence if not classified yet
            conf = 1.0
            b_type = block.block_type

            # Check if block has an explicit semantic annotation
            s_anno = anno_map.get(block.block_id)
            if s_anno:
                conf = s_anno.confidence.score
                b_type = s_anno.assigned_type

            sum_confidence += conf

            if conf < 0.60:
                low_confidence_count += 1

            if b_type == BlockType.UNKNOWN:
                unknown_blocks_count += 1

        avg_confidence = (sum_confidence / total_blocks) if total_blocks > 0 else 1.0
        r_unknown = (unknown_blocks_count / total_blocks) if total_blocks > 0 else 0.0

        # Adjust score for average confidence and unknown ratios
        semantic_score = avg_confidence * (1.0 - r_unknown)
        semantic_score = max(0.0, min(1.0, semantic_score))

        if low_confidence_count > 0:
            warnings.append({
                "warning_code": "LOW_SEMANTIC_CONFIDENCE",
                "severity": "WARNING" if low_confidence_count > total_blocks * 0.2 else "INFO",
                "message": f"Detected {low_confidence_count} blocks with semantic classification confidence below 60%.",
                "target_id": doc.upload_id,
            })

        if r_unknown > 0.15:
            warnings.append({
                "warning_code": "EXCESSIVE_UNKNOWN_BLOCKS",
                "severity": "WARNING",
                "message": f"Excessive blocks classified as UNKNOWN structure: {r_unknown * 100:.1f}%",
                "target_id": doc.upload_id,
            })

        return {
            "score": semantic_score,
            "warnings": warnings,
            "recommendations": recommendations,
        }
