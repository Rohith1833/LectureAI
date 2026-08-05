from typing import List, Tuple
from app.schemas.document import DocumentExtractionResult, BlockSchema, BlockType
from app.services.normalization.base import (
    BaseNormalizer,
    NormalizationContext,
    StageResult,
    StageMetrics,
    TransformationRecord,
)
from app.core.config import settings

# Suffixes/Punctuation that indicate a sentence is complete
SENTENCE_ENDERS = (".", "!", "?")


class ParagraphNormalizer(BaseNormalizer):
    """Merges consecutive paragraph text blocks split by line layout wraps or page transitions."""

    def get_name(self) -> str:
        return "PARAGRAPH_NORMALIZER"

    def run(
        self, doc: DocumentExtractionResult, context: NormalizationContext
    ) -> StageResult:
        updated_blocks: List[BlockSchema] = []
        transformations: List[TransformationRecord] = []
        modified_count = 0
        merged_count = 0
        removed_count = 0

        # 1. Clean soft line breaks within each block first
        blocks = []
        for b in doc.blocks:
            old_text = b.text
            if not old_text or b.block_type != BlockType.PARAGRAPH:
                blocks.append(b)
                continue

            cleaned_text = self._clean_inner_soft_breaks(old_text)
            if cleaned_text != old_text:
                record = TransformationRecord.create_record(
                    step_name=self.get_name(),
                    target_block_id=b.block_id,
                    action="modified",
                    reason="Removed soft line break",
                    original_text=old_text,
                    transformed_text=cleaned_text,
                    verbose=context.debug_mode,
                )
                transformations.append(record)
                modified_count += 1
                b_copy = b.model_copy()
                b_copy.text = cleaned_text
                blocks.append(b_copy)
            else:
                blocks.append(b)

        # 2. Merge consecutive blocks split by layout lines or page breaks
        skip_indices = set()
        final_blocks = []

        for i in range(len(blocks)):
            if i in skip_indices:
                continue

            current_block = blocks[i]
            if current_block.block_type != BlockType.PARAGRAPH:
                final_blocks.append(current_block)
                continue

            active_text = current_block.text
            active_bbox = current_block.bounding_box

            # Check next blocks in order to see if we can merge them
            next_idx = i + 1
            while next_idx < len(blocks):
                next_block = blocks[next_idx]
                if next_block.block_type != BlockType.PARAGRAPH:
                    break

                # Heuristic evaluations
                same_page = next_block.page_number == current_block.page_number
                cross_page = (
                    settings.CROSS_PAGE_MERGE_ENABLED
                    and next_block.page_number == current_block.page_number + 1
                )

                # Check same font family and similar size
                font_matches = (
                    current_block.font_family == next_block.font_family
                    and abs((current_block.font_size or 0) - (next_block.font_size or 0)) <= 0.5
                )

                # Check indentation (left align)
                indent_matches = (
                    abs(active_bbox.x0 - next_block.bounding_box.x0) <= settings.INDENT_TOLERANCE
                )

                # Check block A is unfinished
                stripped_active = active_text.strip().rstrip('"\')')
                unfinished = not stripped_active.endswith(SENTENCE_ENDERS)

                # Check block B begins lowercase or obvious continuation
                stripped_next = next_block.text.strip()
                starts_lowercase = (
                    stripped_next
                    and (stripped_next[0].islower() or stripped_next[0] in (",", ";", ":", "-"))
                )

                # Check layout distance if on the same page
                layout_distance_matches = False
                if same_page:
                    vertical_gap = next_block.bounding_box.y0 - active_bbox.y1
                    layout_distance_matches = 0 <= vertical_gap <= settings.MAX_VERTICAL_GAP

                # Decide if merge is valid
                can_merge = False
                reason = ""
                if font_matches and indent_matches and unfinished and starts_lowercase:
                    if same_page and layout_distance_matches:
                        can_merge = True
                        reason = "Merged paragraph continuation"
                    elif cross_page:
                        can_merge = True
                        reason = "Merged cross-page paragraph"

                if can_merge:
                    # Concatenate block texts with a single space
                    merged_text = f"{active_text} {next_block.text}"

                    # Log transformations
                    transformations.append(
                        TransformationRecord.create_record(
                            step_name=self.get_name(),
                            target_block_id=current_block.block_id,
                            action="modified",
                            reason=reason,
                            original_text=active_text,
                            transformed_text=merged_text,
                            verbose=context.debug_mode,
                        )
                    )
                    transformations.append(
                        TransformationRecord.create_record(
                            step_name=self.get_name(),
                            target_block_id=next_block.block_id,
                            action="deleted",
                            reason="Paragraph block merged into previous block",
                            original_text=next_block.text,
                            transformed_text="",
                            verbose=context.debug_mode,
                        )
                    )

                    # Update current variables to continue merging chain
                    active_text = merged_text
                    # Merge bounding boxes
                    active_bbox.y1 = max(active_bbox.y1, next_block.bounding_box.y1)
                    active_bbox.x1 = max(active_bbox.x1, next_block.bounding_box.x1)
                    active_bbox.x0 = min(active_bbox.x0, next_block.bounding_box.x0)

                    skip_indices.add(next_idx)
                    merged_count += 1
                    removed_count += 1
                    next_idx += 1
                else:
                    break

            if current_block.text != active_text:
                b_copy = current_block.model_copy()
                b_copy.text = active_text
                b_copy.bounding_box = active_bbox
                final_blocks.append(b_copy)
                modified_count += 1
            else:
                final_blocks.append(current_block)

        doc_copy = doc.model_copy()
        doc_copy.blocks = final_blocks

        metrics = StageMetrics(
            execution_time_ms=0.0,
            modified_blocks_count=modified_count,
            merged_blocks_count=merged_count,
            removed_blocks_count=removed_count,
        )

        return StageResult(document=doc_copy, transformations=transformations, metrics=metrics)

    def _clean_inner_soft_breaks(self, text: str) -> str:
        """Removes inner soft line breaks, replacing single newlines with spaces."""
        lines = text.split("\n")
        if len(lines) <= 1:
            return text

        result_lines = []
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped:
                result_lines.append("\n")
                continue

            if i == len(lines) - 1:
                result_lines.append(line_stripped)
            else:
                next_line = lines[i + 1].strip()
                # Check if current line is unfinished and next line starts lowercase
                unfinished = not line_stripped.rstrip('"\')').endswith(SENTENCE_ENDERS)
                starts_lowercase = (
                    next_line
                    and (next_line[0].islower() or next_line[0] in (",", ";", ":", "-"))
                )

                if unfinished and starts_lowercase:
                    result_lines.append(line_stripped + " ")
                else:
                    result_lines.append(line_stripped + "\n")

        return "".join(result_lines).strip()
