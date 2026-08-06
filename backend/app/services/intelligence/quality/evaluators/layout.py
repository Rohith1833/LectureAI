import math
from typing import Dict, List, Any
from collections import defaultdict
from app.services.intelligence.context import IntelligenceContext
from app.services.intelligence.features import FeatureAnnotation
from app.services.intelligence.quality.evaluators.base import BaseQualityEvaluator


class LayoutQualityEvaluator(BaseQualityEvaluator):
    """Evaluates geometric layout uniformity, overlapping boundaries, spacing consistency, and block merges/splits."""

    @property
    def name(self) -> str:
        return "layout_quality"

    def evaluate(self, context: IntelligenceContext) -> Dict[str, Any]:
        doc = context.document
        warnings: List[Dict[str, Any]] = []
        recommendations: List[Dict[str, Any]] = []

        if not doc or not doc.blocks:
            return {"score": 1.0, "warnings": [], "recommendations": []}

        feature_annos = context.annotation_store.find_by_type(FeatureAnnotation)
        anno_map = {a.target_id: a for a in feature_annos}

        total_blocks = len(doc.blocks)
        empty_blocks = 0
        overlapping_pairs = 0
        merged_blocks_count = 0
        split_blocks_count = 0

        # Group blocks by page to check overlaps & spacing consistency
        page_blocks_map = defaultdict(list)
        for block in doc.blocks:
            page_blocks_map[block.page_number].append(block)

        # 1. Analyze empty blocks, size splits/merges, and overlaps
        heights = []
        for block in doc.blocks:
            bbox = block.bounding_box
            if bbox:
                h = bbox.y1 - bbox.y0
                if h > 0:
                    heights.append(h)

        avg_height = sum(heights) / len(heights) if heights else 15.0

        for block in doc.blocks:
            text_stripped = (block.text or "").strip()
            if not text_stripped:
                empty_blocks += 1

            bbox = block.bounding_box
            if bbox:
                h = bbox.y1 - bbox.y0
                w = bbox.x1 - bbox.x0
                word_count = len(text_stripped.split())

                # Merged blocks check: abnormally tall with high word count and no structure split
                if h > avg_height * 4.0 and word_count > 60:
                    merged_blocks_count += 1
                    warnings.append({
                        "warning_code": "MERGED_LAYOUT_BLOCK",
                        "severity": "WARNING",
                        "message": f"Block {block.block_id} has abnormal height ({h:.1f}) and high word count; separate segments might be merged.",
                        "target_id": block.block_id,
                    })

                # Split blocks check: very short with very few words (isolated fragments)
                if h < avg_height * 0.6 and word_count > 0 and word_count <= 3:
                    split_blocks_count += 1
                    warnings.append({
                        "warning_code": "SPLIT_LAYOUT_BLOCK",
                        "severity": "INFO",
                        "message": f"Block {block.block_id} represents a small text fragment; possible split layout line.",
                        "target_id": block.block_id,
                    })

        # 2. Page-level Overlaps and Spacing variance
        spacing_variances = []
        for page_num, p_blocks in page_blocks_map.items():
            # Check overlaps
            for i in range(len(p_blocks)):
                for j in range(i + 1, len(p_blocks)):
                    b1 = p_blocks[i].bounding_box
                    b2 = p_blocks[j].bounding_box
                    if b1 and b2:
                        # Compute intersection
                        ix0 = max(b1.x0, b2.x0)
                        iy0 = max(b1.y0, b2.y0)
                        ix1 = min(b1.x1, b2.x1)
                        iy1 = min(b1.y1, b2.y1)
                        if ix1 > ix0 and iy1 > iy0:
                            # Intersection area
                            i_area = (ix1 - ix0) * (iy1 - iy0)
                            a1 = (b1.x1 - b1.x0) * (b1.y1 - b1.y0)
                            a2 = (b2.x1 - b2.x0) * (b2.y1 - b2.y0)
                            overlap_ratio = i_area / min(a1, a2)
                            if overlap_ratio > 0.15:  # Overlaps significantly
                                overlapping_pairs += 1

            # Spacing variance: Sort blocks vertically
            sorted_blocks = sorted(p_blocks, key=lambda b: b.bounding_box.y0 if b.bounding_box else 0.0)
            margins = []
            for k in range(len(sorted_blocks) - 1):
                box1 = sorted_blocks[k].bounding_box
                box2 = sorted_blocks[k + 1].bounding_box
                if box1 and box2:
                    gap = box2.y0 - box1.y1
                    if gap >= 0:
                        margins.append(gap)

            if len(margins) > 1:
                mean_gap = sum(margins) / len(margins)
                variance = sum((g - mean_gap) ** 2 for g in margins) / len(margins)
                std_dev = math.sqrt(variance)
                # Normalize std_dev relative to mean_gap
                norm_variance = min(1.0, std_dev / max(5.0, mean_gap))
                spacing_variances.append(norm_variance)

        r_empty = empty_blocks / total_blocks
        r_overlap = min(1.0, overlapping_pairs / total_blocks)
        r_spacing = sum(spacing_variances) / len(spacing_variances) if spacing_variances else 0.0
        r_merge_split = (merged_blocks_count + split_blocks_count) / total_blocks

        # Weights configuration
        w_e = 0.2
        w_o = 0.3
        w_s = 0.2
        w_m = 0.3

        layout_penalty = (w_e * r_empty) + (w_o * r_overlap) + (w_s * r_spacing) + (w_m * r_merge_split)
        layout_score = 1.0 - min(1.0, layout_penalty)

        if overlapping_pairs > 0:
            warnings.append({
                "warning_code": "OVERLAPPING_LAYOUT_ELEMENTS",
                "severity": "WARNING",
                "message": f"Detected {overlapping_pairs} overlapping bounding box pairs across pages.",
                "target_id": doc.upload_id,
            })

        if r_spacing > 0.40:
            warnings.append({
                "warning_code": "INCONSISTENT_LAYOUT_SPACING",
                "severity": "INFO",
                "message": "Vertical block spacing variance is high; possible layout structure anomalies.",
                "target_id": doc.upload_id,
            })

        if layout_score < 0.70:
            recommendations.append({
                "recommendation_code": "MANUAL_REVIEW_REQUIRED",
                "severity": "WARNING",
                "message": "Layout scoring failed validation checks. Manual coordinate verification is required.",
                "target_id": doc.upload_id,
            })

        return {
            "score": layout_score,
            "warnings": warnings,
            "recommendations": recommendations,
        }
