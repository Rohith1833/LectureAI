import re
from typing import List, Tuple
from app.schemas.document import DocumentExtractionResult, BlockSchema
from app.services.normalization.base import (
    BaseNormalizer,
    NormalizationContext,
    StageResult,
    StageMetrics,
    TransformationRecord,
)
from app.core.config import settings

# Precompile regex to match within-block line-break hyphenations
# Matches a word character, followed by a hyphen, a newline, and a word character
WITHIN_BLOCK_HYPHEN_RE = re.compile(r"(\w+)-\n(\w+)")


class HyphenationNormalizer(BaseNormalizer):
    """Repairs line-break hyphenations within and across layout blocks using layout structure."""

    def get_name(self) -> str:
        return "HYPHENATION_NORMALIZER"

    def run(
        self, doc: DocumentExtractionResult, context: NormalizationContext
    ) -> StageResult:
        if not settings.HYPHEN_MERGE_ENABLED:
            return StageResult(
                document=doc,
                transformations=[],
                metrics=StageMetrics(execution_time_ms=0.0),
            )

        updated_blocks: List[BlockSchema] = []
        transformations: List[TransformationRecord] = []
        modified_count = 0
        removed_count = 0

        # Gather active blocks sequence
        blocks = [b for b in doc.blocks]
        skip_indices = set()

        for i in range(len(blocks)):
            if i in skip_indices:
                continue

            current_block = blocks[i]
            old_text = current_block.text
            if not old_text:
                updated_blocks.append(current_block)
                continue

            new_text = old_text

            # 1. Repair Within-Block Hyphenations
            # If current block text has line-break hyphens: e.g. "informa-\ntion" -> "information"
            matches = WITHIN_BLOCK_HYPHEN_RE.findall(new_text)
            if matches:
                # Replace "word1-\nword2" with "word1word2"
                new_text = WITHIN_BLOCK_HYPHEN_RE.sub(r"\1\2", new_text)

            # 2. Repair Cross-Block Hyphenations (if current block ends with a hyphen)
            # Check if next block is the continuation
            if new_text.endswith("-") and i + 1 < len(blocks) and (i + 1) not in skip_indices:
                next_block = blocks[i + 1]
                next_text = next_block.text

                # Structural checks for cross-block split continuity:
                # - Reading order is sequential
                # - Font family and size match
                # - Horizontal: current block ends on right (large x1), next starts on left (small x0)
                # - Either same page or adjacent pages (cross-page)
                same_page_continuation = (
                    next_block.page_number == current_block.page_number
                    and next_block.reading_order == current_block.reading_order + 1
                    and current_block.bounding_box.x1 > next_block.bounding_box.x0
                )
                cross_page_continuation = (
                    next_block.page_number == current_block.page_number + 1
                    and current_block.font_family == next_block.font_family
                    and abs((current_block.font_size or 0) - (next_block.font_size or 0)) <= 1.0
                )

                if (same_page_continuation or cross_page_continuation) and next_text:
                    # Strip the trailing hyphen and merge
                    base_text = new_text[:-1]
                    # Check if next block starts with lowercase or continuation syllable
                    if next_text[0].islower() or not next_text[0].isalnum():
                        # Structural merge action: append next block text directly to current block
                        merged_text = f"{base_text}{next_text}"

                        # Record transformations for the merge
                        record = TransformationRecord.create_record(
                            step_name=self.get_name(),
                            target_block_id=current_block.block_id,
                            action="modified",
                            reason="Repaired line-break hyphenation",
                            original_text=old_text,
                            transformed_text=merged_text,
                            verbose=context.debug_mode,
                        )
                        transformations.append(record)

                        # Record removal of the absorbed block
                        delete_record = TransformationRecord.create_record(
                            step_name=self.get_name(),
                            target_block_id=next_block.block_id,
                            action="deleted",
                            reason="Empty block after hyphen merge",
                            original_text=next_text,
                            transformed_text="",
                            verbose=context.debug_mode,
                        )
                        transformations.append(delete_record)

                        # Update text and mark next block to be skipped
                        new_text = merged_text
                        skip_indices.add(i + 1)
                        removed_count += 1
                        modified_count += 1

            if new_text != old_text and i not in skip_indices:
                # If within-block hyphenation occurred but wasn't logged yet
                if not any(t.target_block_id == current_block.block_id for t in transformations):
                    record = TransformationRecord.create_record(
                        step_name=self.get_name(),
                        target_block_id=current_block.block_id,
                        action="modified",
                        reason="Repaired line-break hyphenation",
                        original_text=old_text,
                        transformed_text=new_text,
                        verbose=context.debug_mode,
                    )
                    transformations.append(record)
                    modified_count += 1

                b_copy = current_block.model_copy()
                b_copy.text = new_text
                updated_blocks.append(b_copy)
            else:
                updated_blocks.append(current_block)

        doc_copy = doc.model_copy()
        doc_copy.blocks = updated_blocks

        metrics = StageMetrics(
            execution_time_ms=0.0,
            modified_blocks_count=modified_count,
            removed_blocks_count=removed_count,
        )

        return StageResult(document=doc_copy, transformations=transformations, metrics=metrics)
