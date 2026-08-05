import re
from collections import defaultdict
from typing import List, Dict, Set, Tuple
from app.schemas.document import DocumentExtractionResult, BlockSchema, BlockType
from app.services.normalization.base import (
    BaseNormalizer,
    NormalizationContext,
    StageResult,
    StageMetrics,
    TransformationRecord,
)
from app.core.config import settings

# Page number pattern regex: pure numbers, Roman numerals, or Page X phrases
PAGE_NUM_RE = re.compile(
    r"^(\d+|[ivxldcmIVXLDCM]+|page\s+\d+|\d+\s+of\s+\d+)$", re.IGNORECASE
)


class HeaderFooterNormalizer(BaseNormalizer):
    """Automatically detects running headers, footers, and page numbers across pages, removing or classifying them."""

    def get_name(self) -> str:
        return "HEADER_FOOTER_NORMALIZER"

    def run(
        self, doc: DocumentExtractionResult, context: NormalizationContext
    ) -> StageResult:
        updated_blocks: List[BlockSchema] = []
        transformations: List[TransformationRecord] = []
        modified_count = 0
        removed_count = 0

        # We need page sizes to calculate top/bottom relative location.
        # Create page heights map
        page_heights: Dict[int, float] = {}
        for p in doc.pages:
            page_heights[p.page_number] = p.height or 842.0  # default height (A4)

        # Step 1: Document-wide analysis to register running text and page number layouts
        # Key: (text, is_top, is_bottom, x0_approx, y0_approx, font_family, font_size_approx)
        # Value: Set of page numbers where this static block appeared
        static_block_registry: Dict[Tuple, Set[int]] = defaultdict(set)

        # Key: (is_top, is_bottom, x0_approx, y0_approx, font_family, font_size_approx)
        # Value: Set of page numbers where a numeric page-number candidate appeared at this position
        page_num_layout_registry: Dict[Tuple, Set[int]] = defaultdict(set)

        for b in doc.blocks:
            text_cleaned = b.text.strip()
            if not text_cleaned:
                continue

            page_height = page_heights.get(b.page_number, 842.0)
            
            # Determine page relative top/bottom zones (top 20% or bottom 20% of page height)
            is_top = b.bounding_box.y1 <= page_height * 0.20
            is_bottom = b.bounding_box.y0 >= page_height * 0.80

            if not (is_top or is_bottom):
                continue

            # Position signatures (approximate x0/y0 coordinates to nearest 15 points)
            x0_approx = round(b.bounding_box.x0 / 15.0) * 15
            y0_approx = round(b.bounding_box.y0 / 15.0) * 15
            font_sz_approx = round((b.font_size or 0) / 0.5) * 0.5

            # If it's a page number candidate text pattern
            if PAGE_NUM_RE.match(text_cleaned):
                layout_sig = (
                    is_top,
                    is_bottom,
                    x0_approx,
                    y0_approx,
                    b.font_family,
                    font_sz_approx,
                )
                page_num_layout_registry[layout_sig].add(b.page_number)

            # If it is static text candidate
            static_sig = (
                text_cleaned.lower(),
                is_top,
                is_bottom,
                x0_approx,
                y0_approx,
                b.font_family,
                font_sz_approx,
            )
            static_block_registry[static_sig].add(b.page_number)

        # Build sets of identified header/footer/page-number elements/positions
        # Identify running static signatures
        detected_static_signatures: Set[Tuple] = set()
        for sig, pages in static_block_registry.items():
            text_val, is_top, is_bottom, _, _, _, _ = sig
            threshold = (
                settings.HEADER_REPETITION_THRESHOLD
                if is_top
                else settings.FOOTER_REPETITION_THRESHOLD
            )
            if len(pages) >= threshold:
                detected_static_signatures.add(sig)

        # Identify page number position signatures
        detected_page_number_layouts: Set[Tuple] = set()
        for sig, pages in page_num_layout_registry.items():
            is_top, is_bottom, _, _, _, _ = sig
            threshold = (
                settings.HEADER_REPETITION_THRESHOLD
                if is_top
                else settings.FOOTER_REPETITION_THRESHOLD
            )
            if len(pages) >= threshold:
                detected_page_number_layouts.add(sig)

        # Step 2: Iterate and apply deletions or classifications
        for b in doc.blocks:
            text_cleaned = b.text.strip()
            if not text_cleaned:
                updated_blocks.append(b)
                continue

            page_height = page_heights.get(b.page_number, 842.0)
            is_top = b.bounding_box.y1 <= page_height * 0.20
            is_bottom = b.bounding_box.y0 >= page_height * 0.80

            if not (is_top or is_bottom):
                updated_blocks.append(b)
                continue

            x0_approx = round(b.bounding_box.x0 / 15.0) * 15
            y0_approx = round(b.bounding_box.y0 / 15.0) * 15
            font_sz_approx = round((b.font_size or 0) / 0.5) * 0.5

            static_sig = (
                text_cleaned.lower(),
                is_top,
                is_bottom,
                x0_approx,
                y0_approx,
                b.font_family,
                font_sz_approx,
            )
            layout_sig = (
                is_top,
                is_bottom,
                x0_approx,
                y0_approx,
                b.font_family,
                font_sz_approx,
            )

            # Determine layout match categories
            is_page_number = (
                layout_sig in detected_page_number_layouts
                and PAGE_NUM_RE.match(text_cleaned)
            )
            is_static_element = static_sig in detected_static_signatures

            # If block matches any running header, footer, or page number
            if is_page_number or is_static_element:
                # Decide tag category
                if is_page_number:
                    tag_type = BlockType.PAGE_NUMBER
                    reason = "Detected page number"
                elif is_top:
                    tag_type = BlockType.HEADER
                    reason = "Removed repeated header"
                else:
                    tag_type = BlockType.FOOTER
                    reason = "Removed repeated footer"

                # Apply action based on mode
                if settings.HEADER_FOOTER_MODE == "remove":
                    # Record deletion transformation
                    record = TransformationRecord.create_record(
                        step_name=self.get_name(),
                        target_block_id=b.block_id,
                        action="deleted",
                        reason=reason,
                        original_text=b.text,
                        transformed_text="",
                        verbose=context.debug_mode,
                    )
                    transformations.append(record)
                    removed_count += 1
                    # Skip adding block to output sequence
                    continue
                else:
                    # Classify mode: update block type
                    record = TransformationRecord.create_record(
                        step_name=self.get_name(),
                        target_block_id=b.block_id,
                        action="modified",
                        reason=f"Classified as {tag_type.value}",
                        original_text=b.text,
                        transformed_text=b.text,
                        verbose=context.debug_mode,
                    )
                    transformations.append(record)
                    modified_count += 1

                    b_copy = b.model_copy()
                    b_copy.block_type = tag_type
                    updated_blocks.append(b_copy)
            else:
                updated_blocks.append(b)

        doc_copy = doc.model_copy()
        doc_copy.blocks = updated_blocks

        metrics = StageMetrics(
            execution_time_ms=0.0,
            modified_blocks_count=modified_count,
            removed_blocks_count=removed_count,
        )

        return StageResult(document=doc_copy, transformations=transformations, metrics=metrics)
