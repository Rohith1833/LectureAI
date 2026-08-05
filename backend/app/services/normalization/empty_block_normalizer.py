from typing import List, Dict, Any, Tuple
from app.schemas.document import DocumentExtractionResult
from app.services.normalization.base import (
    BaseNormalizer,
    NormalizationContext,
    StageResult,
    StageMetrics,
    TransformationRecord,
)


class EmptyBlockNormalizer(BaseNormalizer):
    """Deletes layout blocks whose text content is empty or contains only whitespace characters."""

    def get_name(self) -> str:
        return "EMPTY_BLOCK_NORMALIZER"

    def run(
        self, doc: DocumentExtractionResult, context: NormalizationContext
    ) -> StageResult:
        retained_blocks = []
        transformations = []
        removed_count = 0

        for b in doc.blocks:
            # Check if block contains text
            if b.text and b.text.strip():
                retained_blocks.append(b)
            else:
                record = TransformationRecord.create_record(
                    step_name=self.get_name(),
                    target_block_id=b.block_id,
                    action="deleted",
                    reason="empty block removed",
                    original_text=b.text,
                    transformed_text="",
                    verbose=context.debug_mode,
                )
                transformations.append(record)
                removed_count += 1

        doc_copy = doc.model_copy()
        doc_copy.blocks = retained_blocks

        metrics = StageMetrics(
            execution_time_ms=0.0,
            removed_blocks_count=removed_count,
        )

        return StageResult(document=doc_copy, transformations=transformations, metrics=metrics)
