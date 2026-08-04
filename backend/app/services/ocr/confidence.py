from typing import List, Dict, Any
from app.schemas.document import BlockSchema


class OCRConfidenceCalculator:
    """Aggregates and calculates granular confidence metrics for characters, words, pages, and documents."""

    @staticmethod
    def calculate_page_confidence(blocks: List[BlockSchema]) -> float:
        """Page confidence is the average block confidence on that page."""
        ocr_blocks = [b for b in blocks if b.provenance == "OCR"]
        if not ocr_blocks:
            return 1.0  # default to 1.0 (perfect) if no OCR content

        total_conf = sum(b.confidence for b in ocr_blocks)
        return round(total_conf / len(ocr_blocks), 3)

    @staticmethod
    def calculate_document_confidence(page_confidences: List[float]) -> float:
        """Document confidence is the average page confidence across all pages processed."""
        if not page_confidences:
            return 1.0

        total_conf = sum(page_confidences)
        return round(total_conf / len(page_confidences), 3)

    @staticmethod
    def build_confidence_metadata(
        words: List[Dict[str, Any]], page_number: int
    ) -> Dict[str, Any]:
        """Compile granular word-level and character-level confidence statistics for auditing."""
        if not words:
            return {
                "page_number": page_number,
                "word_count": 0,
                "average_word_confidence": 1.0,
                "min_word_confidence": 1.0,
            }

        confidences = [w["confidence"] for w in words]
        avg_conf = sum(confidences) / len(confidences)
        min_conf = min(confidences)

        # Segment words into low, medium, high confidence buckets
        low_count = sum(1 for c in confidences if c < 0.6)
        mid_count = sum(1 for c in confidences if 0.6 <= c < 0.85)
        high_count = sum(1 for c in confidences if c >= 0.85)

        return {
            "page_number": page_number,
            "word_count": len(words),
            "average_word_confidence": round(avg_conf, 3),
            "min_word_confidence": round(min_conf, 3),
            "confidence_distribution": {
                "low_less_than_60": low_count,
                "medium_60_to_85": mid_count,
                "high_greater_than_85": high_count,
            },
        }
