import uuid
from typing import List, Dict, Any, Tuple
from app.schemas.document import BlockSchema, BlockType, BoundingBox
from app.services.document_classifier import DocumentClassifier


class OCRLayoutBuilder:
    """Groups word-level OCR coordinates into lines and layout blocks, scaled back to PDF points."""

    def __init__(self, classifier: DocumentClassifier = None):
        self.classifier = classifier or DocumentClassifier()

    def build_layout_blocks(
        self,
        words: List[Dict[str, Any]],
        page_number: int,
        img_size: Tuple[int, int],
        pdf_size: Tuple[float, float],
    ) -> List[BlockSchema]:
        """Group word items by block_num, scale coordinates to PDF points, and classify block types."""
        if not words:
            return []

        img_w, img_h = img_size
        pdf_w, pdf_h = pdf_size

        scale_x = pdf_w / img_w if img_w > 0 else 1.0
        scale_y = pdf_h / img_h if img_h > 0 else 1.0

        # Group words by Tesseract's block_num
        grouped_by_block: Dict[int, List[Dict[str, Any]]] = {}
        for w in words:
            b_num = w.get("block_num", 0)
            grouped_by_block.setdefault(b_num, []).append(w)

        raw_blocks = []

        # Process each block group
        for b_num, block_words in grouped_by_block.items():
            # Group words inside block by line_num
            grouped_by_line: Dict[int, List[Dict[str, Any]]] = {}
            for w in block_words:
                l_num = w.get("line_num", 0)
                grouped_by_line.setdefault(l_num, []).append(w)

            # Reconstruct text by lines sorted in reading direction
            lines = []
            for l_num in sorted(grouped_by_line.keys()):
                line_words = sorted(grouped_by_line[l_num], key=lambda w: w["bbox"][0])
                line_text = " ".join(w["text"] for w in line_words)
                lines.append(line_text)

            block_text = "\n".join(lines).strip()
            if not block_text:
                continue

            # Calculate bounding box coordinates of the block in pixel space
            x0_min = min(w["bbox"][0] for w in block_words)
            y0_min = min(w["bbox"][1] for w in block_words)
            x1_max = max(w["bbox"][2] for w in block_words)
            y1_max = max(w["bbox"][3] for w in block_words)

            # Scale to PDF point coordinates
            pdf_x0 = x0_min * scale_x
            pdf_y0 = y0_min * scale_y
            pdf_x1 = x1_max * scale_x
            pdf_y1 = y1_max * scale_y

            # Estimate font size from average word height in PDF points
            word_heights = [w["bbox"][3] - w["bbox"][1] for w in block_words]
            avg_word_height_px = sum(word_heights) / len(word_heights) if word_heights else 12.0
            font_size = avg_word_height_px * scale_y

            # Calculate average word confidence
            confidences = [w["confidence"] for w in block_words]
            block_conf = sum(confidences) / len(confidences) if confidences else 1.0

            raw_blocks.append(
                {
                    "block_id": str(uuid.uuid4()),
                    "bbox": (pdf_x0, pdf_y0, pdf_x1, pdf_y1),
                    "text": block_text,
                    "font_size": font_size,
                    "font_family": "OCR-Tesseract",
                    "bold": False,
                    "italic": False,
                    "confidence": block_conf,
                }
            )

        # First pass for DocumentClassifier to evaluate stats
        self.classifier.perform_first_pass([raw_blocks])

        # Second pass: classify blocks & create BlockSchemas
        block_schemas = []
        for idx, rb in enumerate(raw_blocks):
            prev_rb = raw_blocks[idx - 1] if idx > 0 else None
            next_rb = raw_blocks[idx + 1] if idx < len(raw_blocks) - 1 else None

            b_type, conf, reasoning = self.classifier.classify_block(
                rb, prev_rb, next_rb, pdf_h
            )

            # Preserve OCR word level confidence or override with classifier confidence
            # Combine them: OCR text reliability (rb["confidence"]) x Layout classification confidence (conf)
            final_confidence = round(rb["confidence"] * conf, 3)

            block_schemas.append(
                BlockSchema(
                    block_id=rb["block_id"],
                    page_number=page_number,
                    reading_order=idx + 1,  # initial sequence order; will be reassessed globally
                    block_type=b_type,
                    text=rb["text"],
                    bounding_box=BoundingBox(
                        x0=rb["bbox"][0], y0=rb["bbox"][1], x1=rb["bbox"][2], y1=rb["bbox"][3]
                    ),
                    font_size=rb["font_size"],
                    font_family=rb["font_family"],
                    bold=rb["bold"],
                    italic=rb["italic"],
                    confidence=final_confidence,
                    provenance="OCR",
                    extra_metadata={"classification_reasoning": reasoning},
                )
            )

        # Dynamically assign heading levels based on sizes distribution
        flat_dicts = []
        for bs in block_schemas:
            # Create dict matching DocumentClassifier expectations
            flat_dicts.append(
                {
                    "block_type": bs.block_type,
                    "font_size": bs.font_size,
                    "heading_level": None,
                }
            )
        self.classifier.assign_heading_levels(flat_dicts)

        # Copy back computed levels
        for idx, bs in enumerate(block_schemas):
            bs.heading_level = flat_dicts[idx]["heading_level"]

        return block_schemas
