from typing import List, Dict, Any, Tuple
from app.schemas.document import DocumentExtractionResult
from app.services.normalization.base import (
    BaseNormalizer,
    NormalizationContext,
    StageResult,
    StageMetrics,
    TransformationRecord,
)

# Deterministic mapping for standard ligatures, curly quotes, ellipses, and en/em dashes
TYPOGRAPHY_MAP = {
    ord("ﬁ"): "fi",
    ord("ﬂ"): "fl",
    ord("ﬀ"): "ff",
    ord("ﬃ"): "ffi",
    ord("ﬄ"): "ffl",
    ord("“"): '"',
    ord("”"): '"',
    ord("„"): '"',
    ord("‘"): "'",
    ord("’"): "'",
    ord("‚"): "'",
    ord("…"): "...",
    ord("–"): "-",  # en dash
    ord("—"): "-",  # em dash
    ord("―"): "-",  # horizontal bar
}

# Mapping for common Unicode non-standard whitespace characters to ASCII space
WHITESPACE_MAP = {
    ord("\xa0"): " ",  # non-breaking space
    ord("\u2002"): " ",  # en space
    ord("\u2003"): " ",  # em space
    ord("\u2009"): " ",  # thin space
}

COMBINED_MAP = {**TYPOGRAPHY_MAP, **WHITESPACE_MAP}


class UnicodeNormalizer(BaseNormalizer):
    """Normalizes typographic characters, quotes, dashes, and non-standard whitespaces to standard forms."""

    def get_name(self) -> str:
        return "UNICODE_NORMALIZER"

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

            # Deterministic translation
            new_text = old_text.translate(COMBINED_MAP)

            if new_text != old_text:
                record = TransformationRecord.create_record(
                    step_name=self.get_name(),
                    target_block_id=b.block_id,
                    action="modified",
                    reason="unicode normalization",
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
