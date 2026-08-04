import math
import re
from typing import List, Dict, Any, Tuple, Optional
from pydantic import BaseModel, Field

from app.schemas.document import BlockType


class ClassifierConfig(BaseModel):
    """Configurable scoring weights and confidence thresholds for the Document Classifier."""

    # Weights for signals
    weight_size: float = 1.5
    weight_bold: float = 1.0
    weight_length: float = 0.8
    weight_case: float = 0.6
    weight_punctuation: float = 1.2
    weight_numbering: float = 1.0
    weight_spacing: float = 0.8
    weight_neighbor: float = 1.0

    # Margins and thresholds
    heading_threshold: float = 0.65  # Confidence >= 0.65 -> promoted to HEADING
    unknown_threshold: float = 0.35  # Confidence < 0.35 -> falls back to UNKNOWN
    body_size_margin: float = 0.75  # margin around dominant size treated as body

    # Header and Footer margins (Y coordinates)
    header_margin: float = 60.0
    footer_margin: float = 60.0


class DocumentFontStats:
    """Document-wide font statistics resolver."""

    def __init__(self):
        self.size_counts: Dict[float, int] = {}
        self.family_counts: Dict[str, int] = {}
        self.char_counts_by_size: Dict[float, int] = {}
        self.dominant_size: float = 10.0
        self.dominant_family: str = "Arial"

    def process_raw_blocks(self, raw_pages_blocks: List[List[Dict[str, Any]]]) -> None:
        """Accumulate font usage metrics across all pages in the document."""
        for page_blocks in raw_pages_blocks:
            for block in page_blocks:
                if block.get("type", 0) != 0:
                    continue  # skip image blocks

                text = block.get("text", "")
                text_len = len(text)
                if text_len == 0:
                    continue

                avg_size = block.get("font_size", 10.0)
                font_family = block.get("font_family", "Arial")

                # Track counts by block
                self.size_counts[avg_size] = self.size_counts.get(avg_size, 0) + 1
                self.family_counts[font_family] = self.family_counts.get(font_family, 0) + 1

                # Track counts by character volume (highly robust body text indicator)
                self.char_counts_by_size[avg_size] = (
                    self.char_counts_by_size.get(avg_size, 0) + text_len
                )

        # Determine dominant body size by character count volume
        if self.char_counts_by_size:
            self.dominant_size = max(
                self.char_counts_by_size, key=self.char_counts_by_size.get  # type: ignore
            )
        elif self.size_counts:
            self.dominant_size = max(self.size_counts, key=self.size_counts.get)  # type: ignore

        if self.family_counts:
            self.dominant_family = max(self.family_counts, key=self.family_counts.get)  # type: ignore


class DocumentClassifier:
    """Multi-feature document layout scoring and classification engine."""

    def __init__(self, config: Optional[ClassifierConfig] = None):
        self.config = config or ClassifierConfig()
        self.stats = DocumentFontStats()

        # Compile common numbering patterns
        self.numbering_patterns = [
            re.compile(r"^chapter\s+\d+", re.IGNORECASE),
            re.compile(r"^part\s+[ivx\d]+", re.IGNORECASE),
            re.compile(r"^section\s+\d+", re.IGNORECASE),
            re.compile(r"^lesson\s+\d+", re.IGNORECASE),
            re.compile(r"^\d+(\.\d+)*\s+[A-Z]"),  # e.g., 1.2.3 Introduction
        ]

    def perform_first_pass(self, raw_pages_blocks: List[List[Dict[str, Any]]]) -> None:
        """Extract dominant document font statistics."""
        self.stats.process_raw_blocks(raw_pages_blocks)

    def classify_block(
        self,
        block: Dict[str, Any],
        prev_block: Optional[Dict[str, Any]],
        next_block: Optional[Dict[str, Any]],
        page_height: float,
    ) -> Tuple[BlockType, float, Dict[str, Any]]:
        """Score layout features for a single block and return classification, confidence, and reasoning."""
        text = block.get("text", "")
        text_stripped = text.strip()
        if not text_stripped:
            return BlockType.UNKNOWN, 1.0, {"reason": "Empty text block"}

        # Position checks: headers & footers
        bbox = block.get("bbox", (0, 0, 0, 0))
        y0, y1 = bbox[1], bbox[3]

        if y1 <= self.config.header_margin:
            return BlockType.HEADER, 0.95, {"reason": "Position in header margin"}
        if y0 >= page_height - self.config.footer_margin:
            return BlockType.FOOTER, 0.95, {"reason": "Position in footer margin"}



        # --- 1. Size Signal ---
        avg_size = block.get("font_size", 10.0)
        dominant_size = self.stats.dominant_size
        size_diff = avg_size - dominant_size

        if size_diff > 4.5:
            size_score = 1.0
        elif size_diff > 2.0:
            size_score = 0.6
        elif abs(size_diff) <= self.config.body_size_margin:
            size_score = -0.5
        elif size_diff < -1.0:
            size_score = -0.8  # footnote / caption
        else:
            size_score = 0.0

        # --- 2. Bold Signal ---
        bold_score = 0.8 if block.get("bold", False) else -0.5

        # --- 3. Text Length and Line Wraps ---
        text_len = len(text_stripped)
        lines = text.split("\n")
        line_count = len(lines)

        if text_len < 40 and line_count == 1:
            length_score = 0.8
        elif text_len < 100 and line_count <= 2:
            length_score = 0.4
        elif text_len > 200 or line_count > 3:
            length_score = -1.0
        else:
            length_score = 0.0

        # --- 4. Case Signal ---
        has_letters = any(c.isalpha() for c in text_stripped)
        if has_letters and text_stripped.isupper():
            case_score = 0.8
        elif has_letters and text_stripped[0].isupper() and not text_stripped.islower():
            case_score = 0.3
        else:
            case_score = -0.2

        # --- 5. Punctuation Signal ---
        # Headings rarely end in standard terminal punctuation
        ends_with_terminal = text_stripped[-1] in (".", "?", "!") if text_stripped else False
        # Count non-alphanumeric punctuation marks
        punc_count = sum(1 for c in text_stripped if not (c.isalnum() or c.isspace()))
        punc_density = punc_count / text_len if text_len > 0 else 0.0

        if ends_with_terminal:
            punctuation_score = -0.6
        elif punc_density > 0.15:
            punctuation_score = -0.5
        else:
            punctuation_score = 0.3

        # --- 6. Numbering Patterns ---
        matched_numbering = False
        for pattern in self.numbering_patterns:
            if pattern.match(text_stripped):
                matched_numbering = True
                break
        numbering_score = 1.0 if matched_numbering else 0.0

        # --- 7. Spacing Signal (Indentation / Margin Gaps) ---
        spacing_score = 0.0
        if prev_block:
            prev_bbox = prev_block.get("bbox", (0, 0, 0, 0))
            prev_y1 = prev_bbox[3]
            gap_before = y0 - prev_y1
            if gap_before > 25.0:
                spacing_score += 0.5
            elif gap_before > 15.0:
                spacing_score += 0.25

        if next_block:
            next_bbox = next_block.get("bbox", (0, 0, 0, 0))
            next_y0 = next_bbox[1]
            gap_after = next_y0 - y1
            if gap_after > 20.0:
                spacing_score += 0.3

        # --- 8. Neighbor Block Context ---
        neighbor_score = 0.0
        # If font size or font family changes compared to neighbors
        if prev_block:
            prev_size = prev_block.get("font_size", 10.0)
            if avg_size > prev_size + 1.5:
                neighbor_score += 0.5
        if next_block:
            next_size = next_block.get("font_size", 10.0)
            if avg_size > next_size + 1.5:
                neighbor_score += 0.5

        # --- Combine Signals with Configured Weights ---
        net_score = (
            (size_score * self.config.weight_size)
            + (bold_score * self.config.weight_bold)
            + (length_score * self.config.weight_length)
            + (case_score * self.config.weight_case)
            + (punctuation_score * self.config.weight_punctuation)
            + (numbering_score * self.config.weight_numbering)
            + (spacing_score * self.config.weight_spacing)
            + (neighbor_score * self.config.weight_neighbor)
        )

        # Standard Sigmoid normalization function for confidence probability with overflow safety
        net_score_capped = max(-20.0, min(20.0, net_score))
        confidence = 1.0 / (1.0 + math.exp(-net_score_capped))

        # --- Classify and Assign Defaults ---
        reasoning = {
            "size_score": round(size_score * self.config.weight_size, 3),
            "bold_score": round(bold_score * self.config.weight_bold, 3),
            "length_score": round(length_score * self.config.weight_length, 3),
            "case_score": round(case_score * self.config.weight_case, 3),
            "punctuation_score": round(punctuation_score * self.config.weight_punctuation, 3),
            "numbering_score": round(numbering_score * self.config.weight_numbering, 3),
            "spacing_score": round(spacing_score * self.config.weight_spacing, 3),
            "neighbor_score": round(neighbor_score * self.config.weight_neighbor, 3),
            "net_score": round(net_score, 3),
            "dominant_size": round(dominant_size, 2),
            "dominant_family": self.stats.dominant_family,
        }

        if confidence >= self.config.heading_threshold:
            b_type = BlockType.HEADING
        else:
            # Check list & caption prefixes next
            list_prefixes = ("•", "-", "*", "o", "▪", "1.", "2.", "3.", "a.", "b.", "c.", "i.", "ii.")
            caption_prefixes = ("figure ", "fig. ", "table ", "tab. ", "image ", "illustration ")

            if text_stripped.startswith(list_prefixes):
                b_type = BlockType.LIST
                reasoning["rule_override"] = "Matched list prefix pattern"
                return b_type, 0.9, reasoning
            elif text_stripped.lower().startswith(caption_prefixes):
                b_type = BlockType.CAPTION
                reasoning["rule_override"] = "Matched caption prefix pattern"
                return b_type, 0.9, reasoning
            elif confidence < self.config.unknown_threshold:
                # Low heading confidence indicates high certainty it's a standard body paragraph
                b_type = BlockType.PARAGRAPH
            else:
                # Medium confidence block falls in the uncertainty zone -> UNKNOWN
                b_type = BlockType.UNKNOWN

        return b_type, round(confidence, 3), reasoning

    def assign_heading_levels(self, blocks: List[Dict[str, Any]]) -> None:
        """Determine hierarchy (heading_level 1 to 6) based on unique heading font sizes."""
        heading_blocks = [b for b in blocks if b.get("block_type") == BlockType.HEADING]
        if not heading_blocks:
            return

        # Fetch unique heading font sizes, sorted descending
        sizes = sorted(list(set(b.get("font_size", 10.0) for b in heading_blocks)), reverse=True)

        for hb in heading_blocks:
            hb_size = hb.get("font_size", 10.0)
            try:
                # 0-indexed index in sorted sizes list determines H1, H2, H3, H4 level
                lvl = sizes.index(hb_size) + 1
                hb["heading_level"] = min(lvl, 6)  # Cap at H6
            except ValueError:
                hb["heading_level"] = 4
