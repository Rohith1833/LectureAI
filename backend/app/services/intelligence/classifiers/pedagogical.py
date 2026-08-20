import time
from typing import Dict, List, Any
from app.services.intelligence.base import BaseIntelligenceModule, ModuleMetadata
from app.services.intelligence.context import IntelligenceContext
from app.services.intelligence.annotations import ConfidenceScore, AcademicAnnotation
from app.services.intelligence.academic_features import AcademicFeature


class PedagogicalClassificationModule(BaseIntelligenceModule):
    """Classifies pedagogical components: Learning Objectives, Summaries, Exercises, and Review Questions."""

    def __init__(self):
        self._metadata = ModuleMetadata(
            name="PEDAGOGICAL_CLASSIFICATION_MODULE",
            version="1.0.0",
            author="LectureAI Core",
            stage="academic_classification",
            priority=140,
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

            academic_type = None
            method = "pedagogical_indicator_rules"
            confidence = 0.85
            reasoning = ""

            if "starts_with_objective" in feat.syntactic_indicators:
                academic_type = "LEARNING_OBJECTIVE"
                reasoning = "Block matched pedagogical learning objective indicator pattern."
            elif "starts_with_summary" in feat.syntactic_indicators:
                academic_type = "SUMMARY"
                reasoning = "Block matched summary prefix keywords pattern."
            elif "starts_with_exercise" in feat.syntactic_indicators:
                academic_type = "EXERCISE"
                reasoning = "Block matched exercise/problems number indicators."

            if academic_type:
                anno = AcademicAnnotation(
                    annotation_id=f"ac_ped_{block.block_id}_{int(time.time())}",
                    target_id=block.block_id,
                    provenance=self.metadata.name,
                    confidence=ConfidenceScore(score=confidence, method=method),
                    academic_type=academic_type,
                    reasoning=reasoning,
                )
                context.annotation_store.add(anno)
