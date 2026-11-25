import uuid
import statistics
from typing import List, Dict, Any, Tuple
from app.schemas.document import BlockSchema, BlockType, BoundingBox
from app.services.document_classifier import DocumentClassifier


class OCRLayoutBuilder:
    """Groups word-level OCR coordinates into paragraphs, tables, and layout blocks, scaled to PDF points."""

    def __init__(self, classifier: DocumentClassifier = None):
        self.classifier = classifier or DocumentClassifier()

    def _detect_tabular_lines(
        self, sorted_lines: List[List[Dict[str, Any]]]
    ) -> Tuple[bool, str]:
        """Detect if a sequence of lines represents a multi-column table and format as pipe-separated rows."""
        if len(sorted_lines) < 2:
            return False, ""

        row_cells: List[List[str]] = []
        multi_col_rows = 0

        for line_words in sorted_lines:
            if not line_words:
                continue
            avg_h = statistics.median(w["bbox"][3] - w["bbox"][1] for w in line_words)
            col_gap_threshold = max(25.0, avg_h * 2.2)

            cells: List[str] = []
            current_cell: List[str] = [line_words[0]["text"]]
            for prev_w, curr_w in zip(line_words, line_words[1:]):
                gap = curr_w["bbox"][0] - prev_w["bbox"][2]
                if gap > col_gap_threshold:
                    cells.append(" ".join(current_cell))
                    current_cell = [curr_w["text"]]
                else:
                    current_cell.append(curr_w["text"])
            cells.append(" ".join(current_cell))

            if len(cells) >= 2:
                multi_col_rows += 1
            row_cells.append(cells)

        if multi_col_rows >= 2 and multi_col_rows >= len(sorted_lines) * 0.6:
            formatted_rows = [" | ".join(cells) for cells in row_cells]
            return True, "\n".join(formatted_rows)

        return False, ""

    def build_layout_blocks(
        self,
        words: List[Dict[str, Any]],
        page_number: int,
        img_size: Tuple[int, int],
        pdf_size: Tuple[float, float],
    ) -> List[BlockSchema]:
        """Group word items by (block_num, par_num), detect tables, scale to PDF points, and classify."""
        if not words:
            return []

        img_w, img_h = img_size
        pdf_w, pdf_h = pdf_size

        scale_x = pdf_w / img_w if img_w > 0 else 1.0
        scale_y = pdf_h / img_h if img_h > 0 else 1.0

        # Group words by (block_num, par_num) to preserve paragraph boundaries
        grouped_by_par: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
        for w in words:
            key = (w.get("block_num", 0), w.get("par_num", 1))
            grouped_by_par.setdefault(key, []).append(w)

        raw_blocks = []

        for par_key, block_words in grouped_by_par.items():
            grouped_by_line: Dict[int, List[Dict[str, Any]]] = {}
            for w in block_words:
                l_num = w.get("line_num", 0)
                grouped_by_line.setdefault(l_num, []).append(w)

            sorted_lines: List[List[Dict[str, Any]]] = []
            lines_text: List[str] = []
            line_heights: List[float] = []

            for l_num in sorted(grouped_by_line.keys()):
                line_words = sorted(grouped_by_line[l_num], key=lambda w: w["bbox"][0])
                sorted_lines.append(line_words)
                lines_text.append(" ".join(w["text"] for w in line_words))
                med_h = statistics.median(w["bbox"][3] - w["bbox"][1] for w in line_words)
                line_heights.append(med_h)

            is_table, table_text = self._detect_tabular_lines(sorted_lines)
            block_text = table_text if is_table else "\n".join(lines_text).strip()
            if not block_text:
                continue

            x0_min = min(w["bbox"][0] for w in block_words)
            y0_min = min(w["bbox"][1] for w in block_words)
            x1_max = max(w["bbox"][2] for w in block_words)
            y1_max = max(w["bbox"][3] for w in block_words)

            pdf_x0 = x0_min * scale_x
            pdf_y0 = y0_min * scale_y
            pdf_x1 = x1_max * scale_x
            pdf_y1 = y1_max * scale_y

            # Use median line height for stable font size estimation
            med_line_h_px = statistics.median(line_heights) if line_heights else 12.0
            font_size = med_line_h_px * scale_y

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
                    "is_table": is_table,
                }
            )

        # Sort raw blocks top-to-bottom, left-to-right before classification
        raw_blocks.sort(key=lambda b: (round(b["bbox"][1] / 15.0), b["bbox"][0]))

        self.classifier.perform_first_pass([raw_blocks])

        block_schemas = []
        for idx, rb in enumerate(raw_blocks):
            prev_rb = raw_blocks[idx - 1] if idx > 0 else None
            next_rb = raw_blocks[idx + 1] if idx < len(raw_blocks) - 1 else None

            if rb.get("is_table"):
                b_type = BlockType.TABLE
                conf = 0.9
                reasoning = {"rule_override": "OCR tabular column alignment detected"}
            else:
                b_type, conf, reasoning = self.classifier.classify_block(
                    rb, prev_rb, next_rb, pdf_h
                )

            final_confidence = round(rb["confidence"] * conf, 3)

            block_schemas.append(
                BlockSchema(
                    block_id=rb["block_id"],
                    page_number=page_number,
                    reading_order=idx + 1,
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

        flat_dicts = [
            {"block_type": bs.block_type, "font_size": bs.font_size, "heading_level": None}
            for bs in block_schemas
        ]
        self.classifier.assign_heading_levels(flat_dicts)
        for idx, bs in enumerate(block_schemas):
            bs.heading_level = flat_dicts[idx]["heading_level"]

        return block_schemas
