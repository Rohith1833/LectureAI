from typing import Any, Dict, List, Optional
import time
import hashlib

from app.schemas.document import DocumentExtractionResult, BlockSchema
from app.services.intelligence.base import BaseIntelligenceModule, ModuleMetadata
from app.services.intelligence.context import IntelligenceContext
from app.services.intelligence.annotations import ConfidenceScore
from app.services.intelligence.features import (
    BlockFeatures,
    TypographyFeatures,
    GeometryFeatures,
    LayoutFeatures,
    StatisticalFeatures,
    ContextFeatures,
    FeatureAnnotation,
)


class FeatureCache:
    """Thread-safe local cache to prevent recalculation of features for unchanged blocks."""

    def __init__(self):
        self._cache: Dict[str, BlockFeatures] = {}

    def get_cache_key(self, block: BlockSchema) -> str:
        # Create unique fingerprint hash based on content and layout geometry coordinates
        raw_sig = (
            f"{block.block_id}:{block.text}:"
            f"{block.bounding_box.x0},{block.bounding_box.y0},"
            f"{block.bounding_box.x1},{block.bounding_box.y1}:"
            f"{block.font_family}:{block.font_size}:{block.bold}:{block.italic}"
        )
        return hashlib.sha256(raw_sig.encode("utf-8")).hexdigest()

    def get(self, block: BlockSchema) -> Optional[BlockFeatures]:
        key = self.get_cache_key(block)
        return self._cache.get(key)

    def set(self, block: BlockSchema, features: BlockFeatures) -> None:
        key = self.get_cache_key(block)
        self._cache[key] = features

    def clear(self) -> None:
        self._cache.clear()


class FeatureExtractionModule(BaseIntelligenceModule):
    """Orchestrates extraction of typography, geometry, layout, statistical, and context features."""

    def __init__(self):
        self._metadata = ModuleMetadata(
            name="FEATURE_EXTRACTION_MODULE",
            version="1.0.0",
            author="LectureAI Core",
            stage="layout_feature_extraction",
            priority=10,
            dependencies=[],
            enabled=True,
        )
        self.cache = FeatureCache()

    @property
    def metadata(self) -> ModuleMetadata:
        return self._metadata

    def initialize(self, config: dict) -> None:
        """Sets up the module; clears the cache if requested."""
        if config.get("clear_cache_on_init", False):
            self.cache.clear()

    def execute(self, context: IntelligenceContext) -> None:
        doc: DocumentExtractionResult = context.document
        if not doc or not doc.blocks:
            return

        # Prepare page heights mapping
        page_heights: Dict[int, float] = {}
        page_widths: Dict[int, float] = {}
        for p in doc.pages:
            page_heights[p.page_number] = p.height or 842.0
            page_widths[p.page_number] = p.width or 595.0

        # Pre-index blocks in reading order per page
        page_blocks: Dict[int, List[BlockSchema]] = {}
        for b in doc.blocks:
            if b.page_number not in page_blocks:
                page_blocks[b.page_number] = []
            page_blocks[b.page_number].append(b)

        # Sort blocks inside each page sequence by reading order index
        for p_num in page_blocks:
            page_blocks[p_num].sort(key=lambda x: x.reading_order)

        # Process each block
        for i, block in enumerate(doc.blocks):
            # 1. Try Cache Lookup
            cached_feat = self.cache.get(block)
            if cached_feat is not None:
                # Annotation ID must be unique per pipeline run
                anno = FeatureAnnotation(
                    annotation_id=f"feat_{block.block_id}_{int(time.time())}",
                    target_id=block.block_id,
                    provenance=self.metadata.name,
                    confidence=ConfidenceScore(score=1.0),
                    features=cached_feat,
                )
                context.annotation_store.add(anno)
                continue

            # Compute Page relative sizing
            page_h = page_heights.get(block.page_number, 842.0)
            page_w = page_widths.get(block.page_number, 595.0)

            # 2. Extract Typography Features
            text_raw = block.text
            typo = TypographyFeatures(
                font_size=block.font_size or 10.0,
                font_family=block.font_family or "Sans-serif",
                bold=block.bold or False,
                italic=block.italic or False,
                is_all_caps=text_raw.isupper(),
                is_title_case=text_raw.istitle(),
                starts_with_capital=bool(text_raw and text_raw[0].isupper()),
                ends_with_punctuation=bool(text_raw and text_raw.strip().endswith((".", "!", "?", ";", ":", ","))),
            )

            # 3. Extract Geometry Features
            width = block.bounding_box.x1 - block.bounding_box.x0
            height = block.bounding_box.y1 - block.bounding_box.y0
            aspect_ratio = width / height if height > 0 else 0.0
            
            # Margins & Alignment heuristic
            margin_l = block.bounding_box.x0
            margin_r = page_w - block.bounding_box.x1
            
            # Simple alignment estimation: if margins are close to balanced, it's centered
            alignment = "left"
            if abs(margin_l - margin_r) < 15.0 and margin_l > 40.0:
                alignment = "center"

            geom = GeometryFeatures(
                x0=block.bounding_box.x0,
                y0=block.bounding_box.y0,
                x1=block.bounding_box.x1,
                y1=block.bounding_box.y1,
                width=width,
                height=height,
                aspect_ratio=aspect_ratio,
                page_position_y=block.bounding_box.y0 / page_h if page_h > 0 else 0.0,
                margin_left=margin_l,
                margin_right=margin_r,
                indentation=margin_l,
                alignment=alignment,
            )

            # 4. Extract Layout Features
            # Locate neighbors on same page
            siblings = page_blocks.get(block.page_number, [])
            sib_idx = siblings.index(block) if block in siblings else -1

            space_above = 0.0
            space_below = 0.0
            is_at_top = True
            is_at_bottom = True

            if sib_idx > 0:
                prev_sib = siblings[sib_idx - 1]
                space_above = max(0.0, block.bounding_box.y0 - prev_sib.bounding_box.y1)
                is_at_top = False
            if sib_idx != -1 and sib_idx < len(siblings) - 1:
                next_sib = siblings[sib_idx + 1]
                space_below = max(0.0, next_sib.bounding_box.y0 - block.bounding_box.y1)
                is_at_bottom = False

            # Estimate lines count & spacing inside the block
            lines = text_raw.split("\n")
            line_count = len(lines)
            line_spacing = height / line_count if line_count > 0 else 0.0

            lay = LayoutFeatures(
                line_spacing=line_spacing,
                paragraph_spacing_above=space_above,
                paragraph_spacing_below=space_below,
                column_index=0,  # Single column estimation default
                total_columns_on_page=1,
                is_at_top=is_at_top,
                is_at_bottom=is_at_bottom,
            )

            # 5. Extract Statistical Features
            char_count = len(text_raw)
            words = text_raw.split()
            word_count = len(words)

            up_ratio = sum(1 for c in text_raw if c.isupper()) / char_count if char_count > 0 else 0.0
            lo_ratio = sum(1 for c in text_raw if c.islower()) / char_count if char_count > 0 else 0.0
            di_ratio = sum(1 for c in text_raw if c.isdigit()) / char_count if char_count > 0 else 0.0
            pu_ratio = sum(1 for c in text_raw if c in '.,!?;:"\'()[]{}') / char_count if char_count > 0 else 0.0
            sy_ratio = sum(1 for c in text_raw if not c.isalnum() and not c.isspace()) / char_count if char_count > 0 else 0.0
            avg_word = sum(len(w) for w in words) / word_count if word_count > 0 else 0.0
            density = char_count / (width * height) if (width * height) > 0 else 0.0

            stat = StatisticalFeatures(
                word_count=word_count,
                char_count=char_count,
                uppercase_ratio=up_ratio,
                lowercase_ratio=lo_ratio,
                digit_ratio=di_ratio,
                punctuation_ratio=pu_ratio,
                symbol_ratio=sy_ratio,
                avg_word_length=avg_word,
                text_density=density,
            )

            # 6. Extract Context Features
            # Context looks across reading order boundaries
            prev_block = doc.blocks[i - 1] if i > 0 else None
            next_block = doc.blocks[i + 1] if i < len(doc.blocks) - 1 else None

            ctx = ContextFeatures(
                prev_block_id=prev_block.block_id if prev_block else None,
                next_block_id=next_block.block_id if next_block else None,
                prev_block_text=prev_block.text if prev_block else None,
                next_block_text=next_block.text if next_block else None,
                prev_block_font_size=prev_block.font_size if prev_block else None,
                next_block_font_size=next_block.font_size if next_block else None,
                prev_block_type=prev_block.block_type.value if prev_block else None,
                next_block_type=next_block.block_type.value if next_block else None,
                parent_heading_id=None,  # Not calculated in extraction stage
            )

            # Combine all features
            features = BlockFeatures(
                typography=typo,
                geometry=geom,
                layout=lay,
                statistical=stat,
                context=ctx,
            )

            # 7. Update Cache and Add Annotation
            self.cache.set(block, features)

            anno = FeatureAnnotation(
                annotation_id=f"feat_{block.block_id}_{int(time.time())}",
                target_id=block.block_id,
                provenance=self.metadata.name,
                confidence=ConfidenceScore(score=1.0),
                features=features,
            )
            context.annotation_store.add(anno)

    def cleanup(self) -> None:
        """Cleans up internal state references."""
        pass
