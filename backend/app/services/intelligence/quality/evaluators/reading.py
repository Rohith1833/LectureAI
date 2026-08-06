from typing import Dict, List, Any
from app.services.intelligence.context import IntelligenceContext
from app.services.intelligence.graph import DocumentReadingGraphAnnotation, ReadingEdgeType
from app.services.intelligence.quality.evaluators.base import BaseQualityEvaluator


class ReadingQualityEvaluator(BaseQualityEvaluator):
    """Evaluates reading order sequence indices, ambiguous layouts, and path flow metrics."""

    @property
    def name(self) -> str:
        return "reading_quality"

    def evaluate(self, context: IntelligenceContext) -> Dict[str, Any]:
        doc = context.document
        warnings: List[Dict[str, Any]] = []
        recommendations: List[Dict[str, Any]] = []

        if not doc or not doc.blocks:
            return {"score": 1.0, "warnings": [], "recommendations": []}

        # Query DocumentReadingGraphAnnotation
        graphs = context.annotation_store.find_by_type(DocumentReadingGraphAnnotation)
        graph_anno = graphs[0] if graphs else None

        reading_score = 1.0
        ambiguous_flow_count = 0
        total_flow_edges = 0

        if graph_anno:
            # Analyze edges of type READING_FLOW / NEXT
            for edge in graph_anno.edges:
                if edge.edge_type in (ReadingEdgeType.READING_FLOW, ReadingEdgeType.NEXT):
                    total_flow_edges += 1
                    # If edge confidence is low (e.g. column separation is fuzzy), increase ambiguity count
                    if edge.confidence < 0.90:
                        ambiguous_flow_count += 1

            if total_flow_edges > 0:
                r_ambiguity = ambiguous_flow_count / total_flow_edges
                reading_score = 1.0 - r_ambiguity
            else:
                reading_score = 1.0

        # Adjust for coordinate jumps (check if vertical reading transitions skip backwards)
        backwards_jumps = 0
        for block in doc.blocks:
            if block.next_block_id:
                next_block = next((b for b in doc.blocks if b.block_id == block.next_block_id), None)
                if next_block and next_block.page_number == block.page_number:
                    b1 = block.bounding_box
                    b2 = next_block.bounding_box
                    if b1 and b2:
                        # If next block is substantially higher on the same page (y0 is much smaller)
                        # excluding multi-column flows
                        if b2.y1 < b1.y0 - 200.0:
                            backwards_jumps += 1

        if backwards_jumps > 0:
            reading_score = max(0.0, reading_score - (backwards_jumps * 0.15))
            warnings.append({
                "warning_code": "BACKWARD_READING_FLOW",
                "severity": "WARNING",
                "message": f"Detected {backwards_jumps} backward reading sequence transitions on pages.",
                "target_id": doc.upload_id,
                "metadata": {"backwards_jumps": backwards_jumps}
            })

        if reading_score < 0.75:
            warnings.append({
                "warning_code": "AMBIGUOUS_READING_FLOW",
                "severity": "WARNING",
                "message": f"Reading path contains high ambiguity (Reading Score: {reading_score:.2f})",
                "target_id": doc.upload_id,
            })

        return {
            "score": reading_score,
            "warnings": warnings,
            "recommendations": recommendations,
        }
