import re
import time
from typing import Dict, List, Optional, Tuple, Any

from app.schemas.document import BlockSchema, BlockType
from app.services.intelligence.base import BaseIntelligenceModule, ModuleMetadata
from app.services.intelligence.context import IntelligenceContext
from app.services.intelligence.annotations import ConfidenceScore, SemanticAnnotation
from app.services.intelligence.features import FeatureAnnotation


class CodeFormulaDetectionModule(BaseIntelligenceModule):
    """Detects and classifies programming code blocks and mathematical equations/formulas using layout and styling signals."""

    def __init__(self):
        self._metadata = ModuleMetadata(
            name="CODE_FORMULA_DETECTION_MODULE",
            version="1.0.0",
            author="LectureAI Core",
            stage="layout_classification",
            priority=80,
            dependencies=[
                "FEATURE_EXTRACTION_MODULE",
                "HEADING_DETECTION_MODULE",
                "LIST_QUOTE_NOTE_DETECTION_MODULE",
                "TABLE_CAPTION_DETECTION_MODULE",
            ],
            enabled=True,
        )

        # Monospace Font Pattern matching
        self.mono_font_pattern = re.compile(
            r"(courier|consolas|mono|menlo|dejavu|lucida)", re.IGNORECASE
        )

        # Programming keywords
        self.code_keyword_pattern = re.compile(
            r"\b(def|import|class|function|return|let|const|var|public|private|void|struct|package|namespace)\b"
        )

        # LaTeX inline or block equation markers
        self.latex_wrap_pattern = re.compile(
            r"(^\$\$.*\$\$$)|(^\\\[.*\\\]$)|(^\\\(.*\\\)$)", re.DOTALL
        )

        # Standard LaTeX math operators and keywords
        self.latex_math_pattern = re.compile(
            r"\\[a-zA-Z]+\b|[\+\-\*/\^=<>~]"
        )

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

        code_blocks: List[Tuple[BlockSchema, float, Dict[str, Any]]] = []
        equation_blocks: List[Tuple[BlockSchema, float, Dict[str, Any]]] = []

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
                BlockType.TABLE,
                BlockType.CAPTION,
            ):
                continue

            anno = anno_map.get(block.block_id)
            if not anno:
                continue

            text_stripped = block.text.strip()
            if not text_stripped:
                continue

            feats = anno.features

            # --- Target A: Code Detection ---
            is_mono = bool(self.mono_font_pattern.search(block.font_family))
            has_code_keywords = bool(self.code_keyword_pattern.search(text_stripped))
            
            # Syntax Character density
            syntax_chars = {"{", "}", ";", "=>", "!=", "==", "[]", "()"}
            syntax_count = sum(1 for c in text_stripped if c in syntax_chars)
            syntax_ratio = syntax_count / len(text_stripped) if text_stripped else 0.0

            # Promote to CODE if it's monospace and has keywords, OR has high syntax density/characters
            if (is_mono and has_code_keywords) or (is_mono and syntax_count >= 2) or (has_code_keywords and syntax_ratio > 0.05):
                code_blocks.append((block, 0.90, {"reason": "Matches programming syntax and monospaced layout"}))
                continue

            # --- Target B: Formula / Equation Detection ---
            # Latex wraps check
            has_latex_wrap = bool(self.latex_wrap_pattern.match(text_stripped))

            # Math command and symbol density check
            math_matches = self.latex_math_pattern.findall(text_stripped)
            math_word_ratio = len(math_matches) / feats.statistical.word_count if feats.statistical.word_count > 0 else 0.0

            # Math symbol density ratio (fraction of characters that are operators/brackets/digits/spaces)
            math_chars = set("=+-*/^()[]{}<>~0123456789\\ \t\n")
            math_char_count = sum(1 for c in text_stripped if c in math_chars or not c.isalnum())
            math_char_ratio = math_char_count / len(text_stripped) if text_stripped else 0.0

            if has_latex_wrap or (len(math_matches) >= 3 and math_word_ratio > 0.8) or (math_char_ratio > 0.85 and len(text_stripped) < 100):
                equation_blocks.append((block, 0.95, {"reason": "LaTeX markers or mathematical symbol layout density"}))
                continue

        # Save and Update Block Classifications
        self._register_and_write(context, code_blocks, BlockType.CODE)
        self._register_and_write(context, equation_blocks, BlockType.EQUATION)

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
