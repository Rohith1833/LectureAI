import re
from typing import List, Dict, Any, Tuple
from app.schemas.document import DocumentExtractionResult
from app.services.normalization.base import (
    BaseNormalizer,
    NormalizationContext,
    StageResult,
    StageMetrics,
    TransformationRecord,
)

# Precompile reusable regex patterns at module scope for performance optimization
MULTIPLE_SPACES_RE = re.compile(r" +")


class WhitespaceNormalizer(BaseNormalizer):
    """Trims margins, collapses duplicated spaces, normalizes line endings, and limits consecutive blank lines."""

    def get_name(self) -> str:
        return "WHITESPACE_NORMALIZER"

    def run(
        self, doc: DocumentExtractionResult, context: NormalizationContext
    ) -> StageResult:
        updated_blocks = []
        transformations = []
        modified_count = 0

        for b in doc.blocks:
            old_text = b.text
            if not old_text:
                updated_blocks.append(b)
                continue

            # 1. Normalize line endings to standard Unix newline \n
            text = old_text.replace("\r\n", "\n").replace("\r", "\n")

            # 2. Replace tabs with spaces
            text = text.replace("\t", " ")

            # 3. Collapse multiple spaces into a single space
            text = MULTIPLE_SPACES_RE.sub(" ", text)

            # 4. Trim individual lines and collapse blank lines
            raw_lines = text.split("\n")
            trimmed_lines = [line.strip() for line in raw_lines]

            collapsed_lines = []
            prev_empty = False
            for line in trimmed_lines:
                if not line:
                    if not prev_empty:
                        collapsed_lines.append("")
                        prev_empty = True
                else:
                    collapsed_lines.append(line)
                    prev_empty = False

            # Join lines and perform overall block trimming
            new_text = "\n".join(collapsed_lines).strip()

            if new_text != old_text:
                record = TransformationRecord.create_record(
                    step_name=self.get_name(),
                    target_block_id=b.block_id,
                    action="modified",
                    reason="whitespace normalization",
                    original_text=old_text,
                    transformed_text=new_text,
                    verbose=context.debug_mode,
                )
                transformations.append(record)
                modified_count += 1

                b_copy = b.model_copy()
                b_copy.text = new_text
                updated_blocks.append(b_copy)
            else:
                updated_blocks.append(b)

        doc_copy = doc.model_copy()
        doc_copy.blocks = updated_blocks

        metrics = StageMetrics(
            execution_time_ms=0.0,
            modified_blocks_count=modified_count,
        )

        return StageResult(document=doc_copy, transformations=transformations, metrics=metrics)
