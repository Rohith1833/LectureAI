import unicodedata
from typing import List, Dict, Any, Tuple
from app.schemas.document import DocumentExtractionResult
from app.services.normalization.base import (
    BaseNormalizer,
    NormalizationContext,
    StageResult,
    StageMetrics,
    TransformationRecord,
)


class ControlCharacterNormalizer(BaseNormalizer):
    """Filters out invisible, control, and non-printable Unicode characters (except safe whitespace like tabs/newlines)."""

    def get_name(self) -> str:
        return "CONTROL_CHARACTER_NORMALIZER"

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

            # Remove Cc (Other, Control) and Cf (Other, Format) categories, retaining \n, \r, \t
            new_char_list = []
            for c in old_text:
                if c in ("\n", "\r", "\t") or unicodedata.category(c) not in ("Cc", "Cf"):
                    new_char_list.append(c)

            new_text = "".join(new_char_list)

            if new_text != old_text:
                record = TransformationRecord.create_record(
                    step_name=self.get_name(),
                    target_block_id=b.block_id,
                    action="modified",
                    reason="removed control characters",
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
