import re
import time
from typing import Dict, List, Optional, Tuple, Any

from app.schemas.document import BlockSchema, BlockType
from app.services.intelligence.base import BaseIntelligenceModule, ModuleMetadata
from app.services.intelligence.context import IntelligenceContext
from app.services.intelligence.annotations import ConfidenceScore, SemanticAnnotation
from app.services.intelligence.features import FeatureAnnotation


class TableCaptionDetectionModule(BaseIntelligenceModule):
    """Detects and classifies text-based tables and figure/table captions using layout signals."""

    def __init__(self):
        self._metadata = ModuleMetadata(
            name="TABLE_CAPTION_DETECTION_MODULE",
            version="1.0.0",
            author="LectureAI Core",
            stage="layout_classification",
            priority=70,
            dependencies=[
                "FEATURE_EXTRACTION_MODULE",
                "HEADING_DETECTION_MODULE",
                "LIST_QUOTE_NOTE_DETECTION_MODULE",
            ],
            enabled=True,
        )

        # Regex for captions
        self.caption_prefix_pattern = re.compile(
            r"^(figure|fig|table|map|chart|illustration|diagram)\s+\d+", re.IGNORECASE
        )

        # Regex for spacing column separators in tables
        self.table_row_pattern = re.compile(r"\s{3,}")

    @property
    def metadata(self) -> ModuleMetadata:
        return self._metadata

    def execute(self, context: IntelligenceContext) -> None:
        doc = context.document
        if not doc or not doc.blocks:
            return

        # Fetch precomputed features
        feature_annos = context.annotation_store.find_by_type(FeatureAnnotation)
        anno_map = {a.target_id: a for a in feature_annos}

        tables_data: List[Tuple[BlockSchema, float, Dict[str, Any]]] = []
        captions_data: List[Tuple[BlockSchema, float, Dict[str, Any]]] = []

        for block in doc.blocks:
            # Skip blocks that were already classified by previous stages
            if block.block_type in (
                BlockType.HEADING,
                BlockType.HEADER,
                BlockType.FOOTER,
                BlockType.PAGE_NUMBER,
                BlockType.LIST,
                BlockType.QUOTE,
                BlockType.FOOTNOTE,
                BlockType.NOTE,
            ):
                continue

            anno = anno_map.get(block.block_id)
            if not anno:
                continue

            text_stripped = block.text.strip()
            if not text_stripped:
                continue

            # --- Target A: Caption Check ---
            # Prefix matches caption words followed by number
            if self.caption_prefix_pattern.match(text_stripped):
                captions_data.append((block, 0.95, {"reason": "Caption prefix pattern matched"}))
                continue

            # --- Target B: Table Grid Check ---
            lines = [line.strip() for line in block.text.split("\n") if line.strip()]
            if len(lines) < 2:
                continue

            table_row_count = 0
            for line in lines:
                # A line is a table row if it contains columns split by >= 3 spaces or | character
                if self.table_row_pattern.search(line) or "|" in line:
                    table_row_count += 1

            # If at least 2 lines and at least 50% of the lines match the row structure
            if table_row_count >= 2 and table_row_count >= len(lines) * 0.5:
                tables_data.append(
                    (block, 0.90, {"reason": f"Tabular row structure detected in {table_row_count}/{len(lines)} lines"})
                )
                continue

        # Save and Update Block Classifications
        self._register_and_write(context, tables_data, BlockType.TABLE)
        self._register_and_write(context, captions_data, BlockType.CAPTION)

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
