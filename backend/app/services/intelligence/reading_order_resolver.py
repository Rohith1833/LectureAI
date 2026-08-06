import time
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

from app.schemas.document import BlockSchema, BlockType
from app.services.intelligence.base import BaseIntelligenceModule, ModuleMetadata
from app.services.intelligence.context import IntelligenceContext
from app.services.intelligence.annotations import ConfidenceScore, ReadingOrderAnnotation
from app.services.intelligence.features import FeatureAnnotation


class ReadingOrderIntelligenceModule(BaseIntelligenceModule):
    """Reconstructs logical reading order sequence across columns and pages using layout signals."""

    def __init__(self):
        self._metadata = ModuleMetadata(
            name="READING_ORDER_INTELLIGENCE_MODULE",
            version="1.0.0",
            author="LectureAI Core",
            stage="reading_order_resolution",
            priority=90,
            dependencies=["FEATURE_EXTRACTION_MODULE"],
            enabled=True,
        )

    @property
    def metadata(self) -> ModuleMetadata:
        return self._metadata

    def initialize(self, config: dict) -> None:
        pass

    def execute(self, context: IntelligenceContext) -> None:
        doc = context.document
        if not doc or not doc.blocks:
            return

        # Ensure raw parser extraction index is preserved in extra_metadata before reordering
        for orig_idx, block in enumerate(doc.blocks):
            if not block.extra_metadata:
                block.extra_metadata = {}
            if "original_parser_order" not in block.extra_metadata:
                block.extra_metadata["original_parser_order"] = orig_idx

        # 1. Group blocks by page_number
        page_blocks_map = defaultdict(list)
        for block in doc.blocks:
            page_blocks_map[block.page_number].append(block)

        global_sorted_blocks: List[BlockSchema] = []
        block_column_map: Dict[str, int] = {}

        # 2. Sort blocks page-by-page
        for page_num in sorted(page_blocks_map.keys()):
            blocks_on_page = page_blocks_map[page_num]
            
            # Fetch page dimensions (default to 600x800 if page_metadata is missing)
            page_meta = context.page_metadata.get(page_num)
            page_width = page_meta.width if page_meta else 600.0
            page_height = page_meta.height if page_meta else 800.0
            mid_x = page_width / 2.0

            headers = []
            footers = []
            body_blocks = []

            for b in blocks_on_page:
                if b.block_type == BlockType.HEADER:
                    headers.append(b)
                elif b.block_type in (BlockType.FOOTER, BlockType.PAGE_NUMBER):
                    footers.append(b)
                else:
                    body_blocks.append(b)

            headers.sort(key=lambda b: (b.bounding_box.y0, b.bounding_box.x0))
            footers.sort(key=lambda b: (b.bounding_box.y0, b.bounding_box.x0))

            # Segment body blocks by column layouts
            left_side = []
            right_side = []
            spanning = []

            for b in body_blocks:
                x0, x1 = b.bounding_box.x0, b.bounding_box.x1
                centroid_x = (x0 + x1) / 2.0
                
                # A block spans if it is wider than 70% of the page
                is_spanning = (x1 - x0) > (page_width * 0.7) or (x0 < (page_width * 0.3) and x1 > (page_width * 0.7))

                if is_spanning:
                    spanning.append(b)
                elif centroid_x < mid_x:
                    left_side.append(b)
                else:
                    right_side.append(b)

            sorted_body = []
            if left_side and right_side:
                # Two-column sorting
                spanning.sort(key=lambda b: b.bounding_box.y0)
                left_side.sort(key=lambda b: b.bounding_box.y0)
                right_side.sort(key=lambda b: b.bounding_box.y0)

                left_idx = 0
                right_idx = 0

                for span in spanning:
                    span_y = span.bounding_box.y0

                    temp_left = []
                    while left_idx < len(left_side) and left_side[left_idx].bounding_box.y0 < span_y:
                        temp_left.append(left_side[left_idx])
                        block_column_map[left_side[left_idx].block_id] = 0
                        left_idx += 1

                    temp_right = []
                    while right_idx < len(right_side) and right_side[right_idx].bounding_box.y0 < span_y:
                        temp_right.append(right_side[right_idx])
                        block_column_map[right_side[right_idx].block_id] = 1
                        right_idx += 1

                    sorted_body.extend(temp_left)
                    sorted_body.extend(temp_right)
                    
                    block_column_map[span.block_id] = 0
                    sorted_body.append(span)

                # Add remaining elements
                for b in left_side[left_idx:]:
                    block_column_map[b.block_id] = 0
                    sorted_body.append(b)
                for b in right_side[right_idx:]:
                    block_column_map[b.block_id] = 1
                    sorted_body.append(b)
            else:
                # Single column fallback
                body_blocks.sort(key=lambda b: (b.bounding_box.y0, b.bounding_box.x0))
                for b in body_blocks:
                    block_column_map[b.block_id] = 0
                sorted_body = body_blocks

            # Combine sorted parts for page
            page_sorted = headers + sorted_body + footers
            
            # Populate header/footer columns as 0
            for b in headers + footers:
                block_column_map[b.block_id] = 0
                
            global_sorted_blocks.extend(page_sorted)

        # 3. Update canonical block order, reading index links, and write annotations
        doc.blocks = global_sorted_blocks

        for idx, block in enumerate(doc.blocks):
            # In-place updates
            block.reading_order = idx
            block.previous_block_id = doc.blocks[idx - 1].block_id if idx > 0 else None
            block.next_block_id = doc.blocks[idx + 1].block_id if idx < len(doc.blocks) - 1 else None

            # Calculate edge confidence based on type
            conf_val = 0.95
            if block.block_type in (BlockType.HEADER, BlockType.FOOTER, BlockType.PAGE_NUMBER):
                conf_val = 0.99

            anno = ReadingOrderAnnotation(
                annotation_id=f"ro_{block.block_id}_{int(time.time())}",
                target_id=block.block_id,
                provenance=self.metadata.name,
                confidence=ConfidenceScore(
                    score=conf_val,
                    contributors={"layout_alignment": conf_val},
                    method="column_layout_geometry",
                ),
                sequence_index=idx,
                column_index=block_column_map.get(block.block_id, 0),
                reading_direction="LTR",
            )
            context.annotation_store.add(anno)
