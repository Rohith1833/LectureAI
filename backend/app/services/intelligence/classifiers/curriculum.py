import time
from typing import Dict, List, Any
from app.schemas.document import BlockType
from app.services.intelligence.base import BaseIntelligenceModule, ModuleMetadata
from app.services.intelligence.context import IntelligenceContext
from app.services.intelligence.annotations import ConfidenceScore, AcademicAnnotation
from app.services.intelligence.academic_features import AcademicFeature


class CurriculumClassificationModule(BaseIntelligenceModule):
    """Classifies Unit, Chapter, Section, and Topic structures based on structural hierarchy depth."""

    def __init__(self):
        self._metadata = ModuleMetadata(
            name="CURRICULUM_CLASSIFICATION_MODULE",
            version="1.0.0",
            author="LectureAI Core",
            stage="academic_classification",
            priority=130,
            dependencies=["ACADEMIC_FEATURE_ENGINE"],
            enabled=True,
        )

    @property
    def metadata(self) -> ModuleMetadata:
        return self._metadata

    def initialize(self, config: dict) -> None:
        pass

    def execute(self, context: IntelligenceContext) -> None:
        doc = context.document
        if not doc or not doc.blocks:
            return

        feature_store: Dict[str, AcademicFeature] = context.shared_cache.get("academic_features", {})

        for block in doc.blocks:
            feat = feature_store.get(block.block_id)
            if not feat:
                continue

            # Classify HEADING blocks into Unit/Chapter/Section/Topic based on hierarchy depth & headings scale
            if feat.semantic_label == BlockType.HEADING:
                academic_type = "SECTION"
                reasoning = f"Heading classified as SECTION due to depth level {feat.heading_depth}."

                if feat.heading_depth == 1:
                    academic_type = "CHAPTER"
                    reasoning = "Heading resolved as CHAPTER (primary depth root)."
                elif feat.heading_depth == 0:
                    academic_type = "UNIT"
                    reasoning = "Heading resolved as UNIT (top-level document separator)."
                elif feat.heading_depth >= 3:
                    academic_type = "TOPIC"
                    reasoning = "Deep heading structure resolved as specific TOPIC."

                anno = AcademicAnnotation(
                    annotation_id=f"ac_cur_{block.block_id}_{int(time.time())}",
                    target_id=block.block_id,
                    provenance=self.metadata.name,
                    confidence=ConfidenceScore(score=0.95, method="hierarchy_depth_classification"),
                    academic_type=academic_type,
                    reasoning=reasoning,
                    metadata={"heading_depth": feat.heading_depth}
                )
                context.annotation_store.add(anno)
            else:
                # Fallback check for text pattern indicating unit/chapter/section/topic
                text = (block.text or "").strip()
                if text.lower().startswith("chapter ") or text.lower().startswith("chap. "):
                    anno = AcademicAnnotation(
                        annotation_id=f"ac_cur_{block.block_id}_{int(time.time())}",
                        target_id=block.block_id,
                        provenance=self.metadata.name,
                        confidence=ConfidenceScore(score=0.90, method="prefix_pattern_classification"),
                        academic_type="CHAPTER",
                        reasoning="Block text starts with 'Chapter' indicator pattern.",
                    )
                    context.annotation_store.add(anno)
                elif text.lower().startswith("unit "):
                    anno = AcademicAnnotation(
                        annotation_id=f"ac_cur_{block.block_id}_{int(time.time())}",
                        target_id=block.block_id,
                        provenance=self.metadata.name,
                        confidence=ConfidenceScore(score=0.90, method="prefix_pattern_classification"),
                        academic_type="UNIT",
                        reasoning="Block text starts with 'Unit' indicator pattern.",
                    )
                    context.annotation_store.add(anno)
