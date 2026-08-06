import re
import time
from typing import Dict, List, Optional, Tuple, Any

from app.schemas.document import BlockSchema, BlockType
from app.services.intelligence.base import BaseIntelligenceModule, ModuleMetadata
from app.services.intelligence.context import IntelligenceContext
from app.services.intelligence.annotations import ConfidenceScore, SemanticAnnotation
from app.services.intelligence.features import FeatureAnnotation


class ListQuoteNoteDetectionModule(BaseIntelligenceModule):
    """Detects and classifies lists, blockquotes, and notes/footnotes using layout signals."""

    def __init__(self):
        self._metadata = ModuleMetadata(
            name="LIST_QUOTE_NOTE_DETECTION_MODULE",
            version="1.0.0",
            author="LectureAI Core",
            stage="layout_classification",
            priority=60,
            dependencies=["FEATURE_EXTRACTION_MODULE", "HEADING_DETECTION_MODULE"],
            enabled=True,
        )

        # Regexes for list items
        self.bullet_pattern = re.compile(
            r"^[\u2022\u25e6\u25aa\u25ab\u25ca\u25cb\u25cf\u25d8\u2023\u2043\u25c9\u25c8\u25a0\u25c6\-•*✦➢▪¶]\s+"
        )
        self.numbered_pattern = re.compile(
            r"^(\d+(\.\d+)*|[a-zA-Z]|[ivxldcmIVXLDCM]+)[\.\)]\s+"
        )
        self.enclosed_pattern = re.compile(
            r"^\((\d+|[a-zA-Z]|[ivxldcmIVXLDCM]+)\)\s+"
        )

        # Regexes for footnotes and notes
        self.footnote_marker_pattern = re.compile(
            r"^(\d+|[*†‡§¶])\s+[A-Za-z]"
        )
        self.note_keyword_pattern = re.compile(
            r"^(note|footnote|source|tip|warning|notice):\s+", re.IGNORECASE
        )

    @property
    def metadata(self) -> ModuleMetadata:
        return self._metadata

    def execute(self, context: IntelligenceContext) -> None:
        doc = context.document
        if not doc or not doc.blocks:
            return

        # 1. Fetch precomputed features from the store
        feature_annos = context.annotation_store.find_by_type(FeatureAnnotation)
        anno_map = {a.target_id: a for a in feature_annos}

        # 2. Compute Document-Wide Statistics (Dominant size, margins, indents)
        size_chars: Dict[float, int] = {}
        indent_counts: Dict[float, int] = {}
        margin_r_counts: Dict[float, int] = {}

        for block in doc.blocks:
            anno = anno_map.get(block.block_id)
            if not anno:
                continue
            geom = anno.features.geometry
            typo = anno.features.typography
            char_cnt = anno.features.statistical.char_count

            size_chars[typo.font_size] = size_chars.get(typo.font_size, 0) + char_cnt
            
            # Count indent and margin alignments to nearest 5 points
            indent_approx = round(geom.margin_left / 5.0) * 5
            margin_r_approx = round(geom.margin_right / 5.0) * 5
            
            indent_counts[indent_approx] = indent_counts.get(indent_approx, 0) + 1
            margin_r_counts[margin_r_approx] = margin_r_counts.get(margin_r_approx, 0) + 1

        dominant_size = max(size_chars, key=size_chars.get) if size_chars else 10.0
        dominant_indent = max(indent_counts, key=indent_counts.get) if indent_counts else 50.0
        dominant_margin_r = max(margin_r_counts, key=margin_r_counts.get) if margin_r_counts else 50.0

        # Mappings of calculated classifications
        lists_data: List[Tuple[BlockSchema, float, Dict[str, Any]]] = []
        quotes_data: List[Tuple[BlockSchema, float, Dict[str, Any]]] = []
        footnotes_data: List[Tuple[BlockSchema, float, Dict[str, Any]]] = []
        notes_data: List[Tuple[BlockSchema, float, Dict[str, Any]]] = []

        # 3. Classify blocks
        for block in doc.blocks:
            # Skip blocks that were already determined as headings, headers, footers, or page numbers
            if block.block_type in (BlockType.HEADING, BlockType.HEADER, BlockType.FOOTER, BlockType.PAGE_NUMBER):
                continue

            anno = anno_map.get(block.block_id)
            if not anno:
                continue

            text_stripped = block.text.strip()
            if not text_stripped:
                continue

            feats = anno.features

            # --- Target A: Note Keyword Check ---
            if self.note_keyword_pattern.match(text_stripped):
                notes_data.append((block, 0.95, {"reason": "Note keyword matched at prefix"}))
                continue

            # --- Target B: Footnote Check ---
            # Bottom region, small font size, and starts with digit or standard footnote mark
            is_bottom = feats.geometry.page_position_y > 0.75
            is_small_font = feats.typography.font_size <= dominant_size - 1.5
            has_marker = bool(
                self.footnote_marker_pattern.match(text_stripped) or 
                (text_stripped and text_stripped[0].isdigit())
            )

            if is_bottom and is_small_font and has_marker:
                footnotes_data.append((block, 0.90, {"reason": "Positioned at bottom margin with footnote marker"}))
                continue

            # --- Target C: List Check ---
            is_list = bool(
                self.bullet_pattern.match(text_stripped) or
                self.numbered_pattern.match(text_stripped) or
                self.enclosed_pattern.match(text_stripped)
            )

            if is_list:
                lists_data.append((block, 0.95, {"reason": "Bullet or list prefix pattern matched"}))
                continue

            # --- Target D: Quote Check ---
            # Quotation marks wraps
            has_quote_wrap = (
                (text_stripped.startswith("“") and text_stripped.endswith("”")) or
                (text_stripped.startswith('"') and text_stripped.endswith('"')) or
                (text_stripped.startswith("‘") and text_stripped.endswith("’"))
            )

            # Indentation wraps (distinct left/right indents relative to page defaults)
            has_quote_indents = (
                feats.geometry.margin_left > dominant_indent + 15.0 and
                feats.geometry.margin_right > 80.0
            )

            # Fully italicized with a left indent
            is_italic_indent = (
                feats.typography.italic and
                feats.geometry.margin_left > dominant_indent + 15.0
            )

            if has_quote_wrap or has_quote_indents or is_italic_indent:
                quotes_data.append((block, 0.85, {"reason": "Matches blockquote indentation and styling"}))
                continue

        # 4. Save and Update Block Classifications
        self._register_and_write(context, lists_data, BlockType.LIST)
        self._register_and_write(context, quotes_data, BlockType.QUOTE)
        self._register_and_write(context, footnotes_data, BlockType.FOOTNOTE)
        self._register_and_write(context, notes_data, BlockType.NOTE)

    def _register_and_write(
        self,
        context: IntelligenceContext,
        blocks_data: List[Tuple[BlockSchema, float, Dict[str, Any]]],
        assigned_type: BlockType
    ) -> None:
        for block, confidence, reasoning in blocks_data:
            # Update canonical block structure in-place
            block.block_type = assigned_type

            # Add semantic annotation
            anno = SemanticAnnotation(
                annotation_id=f"sem_{block.block_id}_{int(time.time())}",
                target_id=block.block_id,
                provenance=self.metadata.name,
                confidence=ConfidenceScore(
                    score=confidence,
                    contributors={"pattern": confidence},
                    method="layout_patterns",
                ),
                assigned_type=assigned_type,
                reasoning=[reasoning.get("reason", "Detected pattern matching")],
            )
            context.annotation_store.add(anno)
