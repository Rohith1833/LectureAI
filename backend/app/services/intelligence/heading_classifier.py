import re
import time
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from app.schemas.document import BlockSchema, BlockType
from app.services.intelligence.base import BaseIntelligenceModule, ModuleMetadata
from app.services.intelligence.context import IntelligenceContext
from app.services.intelligence.annotations import ConfidenceScore, SemanticAnnotation
from app.services.intelligence.features import FeatureAnnotation


class HeadingClassifierConfig(BaseModel):
    """Configurable weights and thresholds for Heading Classifier scoring."""
    weight_size: float = 1.5
    weight_bold: float = 1.0
    weight_length: float = 0.8
    weight_case: float = 0.6
    weight_punctuation: float = 1.2
    weight_numbering: float = 1.0
    weight_spacing: float = 0.8
    weight_alignment: float = 0.6

    heading_threshold: float = 0.65
    unknown_threshold: float = 0.35


class HeadingDetectionModule(BaseIntelligenceModule):
    """Computes heading scores across layout blocks and determines hierarchy and levels."""

    def __init__(self):
        self._metadata = ModuleMetadata(
            name="HEADING_DETECTION_MODULE",
            version="1.0.0",
            author="LectureAI Core",
            stage="layout_classification",
            priority=50,
            dependencies=["FEATURE_EXTRACTION_MODULE"],
            enabled=True,
        )
        self.config = HeadingClassifierConfig()
        
        # Compile common numbering patterns
        self.numbering_patterns = [
            re.compile(r"^chapter\s+\d+", re.IGNORECASE),
            re.compile(r"^part\s+[ivx\d]+", re.IGNORECASE),
            re.compile(r"^section\s+\d+", re.IGNORECASE),
            re.compile(r"^lesson\s+\d+", re.IGNORECASE),
            re.compile(r"^\d+(\.\d+)*\s+[A-Z]"),  # e.g., 1.2.3 Introduction
        ]

    @property
    def metadata(self) -> ModuleMetadata:
        return self._metadata

    def initialize(self, config: dict) -> None:
        # Load weights and thresholds from incoming configurations override
        if config:
            self.config = HeadingClassifierConfig(**config)

    def execute(self, context: IntelligenceContext) -> None:
        doc = context.document
        if not doc or not doc.blocks:
            return

        # 1. Fetch precomputed features from the store
        feature_annos = context.annotation_store.find_by_type(FeatureAnnotation)
        anno_map = {a.target_id: a for a in feature_annos}

        # 2. Document-Wide Font Statistics (Dominant size selection)
        size_chars: Dict[float, int] = {}
        for block in doc.blocks:
            anno = anno_map.get(block.block_id)
            if not anno:
                continue
            f_size = anno.features.typography.font_size
            c_count = anno.features.statistical.char_count
            size_chars[f_size] = size_chars.get(f_size, 0) + c_count

        dominant_size = max(size_chars, key=size_chars.get) if size_chars else 10.0

        # Mappings of calculated confidences and reasoning
        heading_blocks: List[Tuple[BlockSchema, float, Dict[str, Any]]] = []
        body_blocks: List[Tuple[BlockSchema, float, Dict[str, Any]]] = []
        unknown_blocks: List[Tuple[BlockSchema, float, Dict[str, Any]]] = []

        # 3. Classify blocks individually using multi-feature scores
        for block in doc.blocks:
            anno = anno_map.get(block.block_id)
            if not anno:
                # If features are missing, skip or default to Unknown
                unknown_blocks.append((block, 1.0, {"reason": "Features annotation missing"}))
                continue

            text_stripped = block.text.strip()
            if not text_stripped:
                unknown_blocks.append((block, 1.0, {"reason": "Empty text block"}))
                continue

            # If block has no alphanumeric characters, it is layout noise -> classify as UNKNOWN
            has_alphanumeric = any(c.isalnum() for c in text_stripped)
            if not has_alphanumeric:
                unknown_blocks.append((block, 0.0, {"reason": "Contains no alphanumeric characters"}))
                continue

            feats = anno.features

            # --- Signal 1: Size ---
            f_size = feats.typography.font_size
            size_diff = f_size - dominant_size
            if size_diff > 4.5:
                size_score = 1.0
            elif size_diff > 2.0:
                size_score = 0.6
            elif abs(size_diff) <= 0.75:  # within body margin
                size_score = -0.5
            elif size_diff < -1.0:
                size_score = -0.8
            else:
                size_score = 0.0

            # --- Signal 2: Bold ---
            bold_score = 0.8 if feats.typography.bold else -0.5

            # --- Signal 3: Length & Wraps ---
            word_cnt = feats.statistical.word_count
            if word_cnt < 8 and not feats.typography.ends_with_punctuation:
                length_score = 0.8
            elif word_cnt < 15:
                length_score = 0.4
            elif word_cnt > 30:
                length_score = -1.0
            else:
                length_score = 0.0

            # --- Signal 4: Casing ---
            if feats.typography.is_all_caps:
                case_score = 0.8
            elif feats.typography.is_title_case:
                case_score = 0.4
            elif feats.typography.starts_with_capital:
                case_score = 0.2
            else:
                case_score = -0.3

            # --- Signal 5: Punctuation ---
            if feats.typography.ends_with_punctuation and text_stripped[-1] in (".", "?", "!"):
                punctuation_score = -0.6
            elif feats.statistical.punctuation_ratio > 0.15:
                punctuation_score = -0.5
            else:
                punctuation_score = 0.3

            # --- Signal 6: Numbering ---
            matched_num = False
            for pat in self.numbering_patterns:
                if pat.match(text_stripped):
                    matched_num = True
                    break
            numbering_score = 1.0 if matched_num else 0.0

            # --- Signal 7: Spacing ---
            spacing_score = 0.0
            if feats.layout.paragraph_spacing_above > 25.0:
                spacing_score += 0.5
            elif feats.layout.paragraph_spacing_above > 15.0:
                spacing_score += 0.25
            if feats.layout.paragraph_spacing_below > 25.0:
                spacing_score += 0.5
            elif feats.layout.paragraph_spacing_below > 15.0:
                spacing_score += 0.25

            # --- Signal 8: Alignment ---
            alignment_score = 0.6 if feats.geometry.alignment == "center" else 0.0

            # 4. Aggregate Weighted Scores
            signals = {
                "size": (size_score, self.config.weight_size),
                "bold": (bold_score, self.config.weight_bold),
                "length": (length_score, self.config.weight_length),
                "case": (case_score, self.config.weight_case),
                "punctuation": (punctuation_score, self.config.weight_punctuation),
                "numbering": (numbering_score, self.config.weight_numbering),
                "spacing": (spacing_score, self.config.weight_spacing),
                "alignment": (alignment_score, self.config.weight_alignment),
            }

            weighted_sum = 0.0
            weight_total = 0.0
            contributors = {}

            for name, (score, weight) in signals.items():
                weighted_sum += score * weight
                weight_total += abs(weight)
                contributors[name] = score * weight

            # Normalize to [0, 1] range
            # Range of weighted_sum before normalization is [-weight_total, weight_total]
            confidence = (weighted_sum / weight_total + 1.0) / 2.0 if weight_total > 0 else 0.5
            confidence = max(0.0, min(1.0, confidence))

            reasoning = {
                "contributors": contributors,
                "weighted_sum": weighted_sum,
                "weight_total": weight_total,
                "text_snippet": text_stripped[:40]
            }

            # Threshold check
            if confidence >= self.config.heading_threshold:
                heading_blocks.append((block, confidence, reasoning))
            elif confidence < self.config.unknown_threshold:
                unknown_blocks.append((block, confidence, reasoning))
            else:
                body_blocks.append((block, confidence, reasoning))

        # 5. Dynamic Heading Level Resolution (H1-H6 based on sizes of classified headings)
        unique_heading_sizes = sorted(
            list(set(anno_map[b.block_id].features.typography.font_size for b, _, _ in heading_blocks)),
            reverse=True
        )

        size_to_level = {}
        for idx, size in enumerate(unique_heading_sizes):
            # idx=0 represents H1 (largest), capped at H6
            size_to_level[size] = min(idx + 1, 6)

        # 6. Apply promotions and write annotations
        self._register_and_write(
            context, heading_blocks, BlockType.HEADING, size_to_level, anno_map
        )
        self._register_and_write(
            context, body_blocks, BlockType.PARAGRAPH, {}, anno_map
        )
        self._register_and_write(
            context, unknown_blocks, BlockType.UNKNOWN, {}, anno_map
        )

    def _register_and_write(
        self,
        context: IntelligenceContext,
        blocks_data: List[Tuple[BlockSchema, float, Dict[str, Any]]],
        assigned_type: BlockType,
        size_to_level: Dict[float, int],
        anno_map: Dict[str, FeatureAnnotation]
    ) -> None:
        for block, confidence, reasoning in blocks_data:
            # Determine level
            level = None
            if assigned_type == BlockType.HEADING:
                f_size = anno_map[block.block_id].features.typography.font_size
                level = size_to_level.get(f_size, 4)

            # Update the block in-place directly on the document (enables downstream tasks)
            block.block_type = assigned_type
            block.heading_level = level

            # Save semantic annotation
            anno = SemanticAnnotation(
                annotation_id=f"sem_{block.block_id}_{int(time.time())}",
                target_id=block.block_id,
                provenance=self.metadata.name,
                confidence=ConfidenceScore(
                    score=confidence,
                    contributors=reasoning.get("contributors", {}),
                    method="weighted_signals",
                ),
                assigned_type=assigned_type,
                reasoning=[f"Weighted sum: {reasoning['weighted_sum']:.4f}"] if "weighted_sum" in reasoning else [reasoning.get("reason", "No reasoning provided")],
                metadata={"heading_level": level} if level else {},
            )
            context.annotation_store.add(anno)
