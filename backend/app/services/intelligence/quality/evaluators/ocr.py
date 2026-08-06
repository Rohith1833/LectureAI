import re
from typing import Dict, List, Any
from app.services.intelligence.context import IntelligenceContext
from app.services.intelligence.quality.evaluators.base import BaseQualityEvaluator


class OCRQualityEvaluator(BaseQualityEvaluator):
    """Evaluates the confidence, spelling anomalies, and text noise levels of OCR outputs."""

    @property
    def name(self) -> str:
        return "ocr_quality"

    def evaluate(self, context: IntelligenceContext) -> Dict[str, Any]:
        doc = context.document
        warnings: List[Dict[str, Any]] = []
        recommendations: List[Dict[str, Any]] = []

        if not doc or not doc.blocks:
            return {"score": 1.0, "warnings": [], "recommendations": []}

        total_words = 0
        suspicious_words = 0
        garbage_chars = 0
        total_chars = 0
        sum_confidence = 0.0
        block_count = 0

        # Regex for suspicious words: containing mixed digits/letters or bizarre repeating consonants
        suspicious_regex = re.compile(r"(?:\d+[a-zA-Z]|[a-zA-Z]+\d+)|[bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ]{5,}")
        # Non-printable or generic scanning corrupt control character regex
        garbage_regex = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\xff]")

        for block in doc.blocks:
            text = block.text or ""
            text_len = len(text)
            if text_len == 0:
                continue

            total_chars += text_len
            garbage_chars += len(garbage_regex.findall(text))
            
            # Count confidence
            sum_confidence += getattr(block, "confidence", 1.0) or 1.0
            block_count += 1

            words = text.split()
            for word in words:
                total_words += 1
                if suspicious_regex.search(word):
                    suspicious_words += 1

        avg_confidence = (sum_confidence / block_count) if block_count > 0 else 1.0
        r_suspicious = (suspicious_words / total_words) if total_words > 0 else 0.0
        r_garbage = (garbage_chars / total_chars) if total_chars > 0 else 0.0

        # Calculate final OCR score
        ocr_score = avg_confidence * (1.0 - r_suspicious) * (1.0 - r_garbage)
        ocr_score = max(0.0, min(1.0, ocr_score))

        # Generate warnings
        if ocr_score < 0.75:
            warnings.append({
                "warning_code": "POOR_OCR_CONFIDENCE",
                "severity": "CRITICAL" if ocr_score < 0.60 else "WARNING",
                "message": f"Average OCR confidence is extremely low: {ocr_score:.2f}",
                "target_id": doc.upload_id,
                "metadata": {
                    "avg_confidence": avg_confidence,
                    "r_suspicious": r_suspicious,
                    "r_garbage": r_garbage,
                }
            })

        if r_garbage > 0.05:
            warnings.append({
                "warning_code": "EXCESSIVE_GARBAGE_CHARS",
                "severity": "WARNING",
                "message": f"Excessive non-printable/corrupted garbage characters detected: {r_garbage * 100:.1f}%",
                "target_id": doc.upload_id,
                "metadata": {"r_garbage": r_garbage}
            })

        # Generate recommendations
        if ocr_score < 0.70:
            recommendations.append({
                "recommendation_code": "RERUN_OCR_RECOMMENDED",
                "severity": "WARNING",
                "message": "Poor OCR score detected. Running OCR processing with FORCE strategy is recommended.",
                "target_id": doc.upload_id,
            })

        return {
            "score": ocr_score,
            "warnings": warnings,
            "recommendations": recommendations,
        }
