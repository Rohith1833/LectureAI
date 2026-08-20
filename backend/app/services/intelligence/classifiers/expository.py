import time
from typing import Dict, List, Any
from app.services.intelligence.base import BaseIntelligenceModule, ModuleMetadata
from app.services.intelligence.context import IntelligenceContext
from app.services.intelligence.annotations import ConfidenceScore, AcademicAnnotation
from app.services.intelligence.academic_features import AcademicFeature


class ExpositoryClassificationModule(BaseIntelligenceModule):
    """Classifies expository features like Definition, Theorem, Proof, Formula, Algorithm, and Examples."""

    def __init__(self):
        self._metadata = ModuleMetadata(
            name="EXPOSITORY_CLASSIFICATION_MODULE",
            version="1.0.0",
            author="LectureAI Core",
            stage="academic_classification",
            priority=135,
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
            method = "expository_indicator_rules"
            confidence = 0.85
            reasoning = ""

            # Check syntactic indicator anchors
            if "starts_with_definition" in feat.syntactic_indicators:
                academic_type = "DEFINITION"
                reasoning = "Block matches definition indicator prefix pattern."
            elif "starts_with_theorem" in feat.syntactic_indicators:
                academic_type = "THEOREM"
                reasoning = "Block matches theorem indicator prefix pattern."
            elif "starts_with_proof" in feat.syntactic_indicators:
                academic_type = "PROOF"
                reasoning = "Block matches proof indicator prefix pattern."
            elif "starts_with_example" in feat.syntactic_indicators:
                academic_type = "EXAMPLE"
                reasoning = "Block matches example indicator prefix pattern."
            elif feat.contains_mathematical_notation and feat.semantic_label == "EQUATION":
                academic_type = "FORMULA"
                confidence = 0.90
                reasoning = "Mathematical notation found inside semantic equation block."

            if academic_type:
                anno = AcademicAnnotation(
                    annotation_id=f"ac_exp_{block.block_id}_{int(time.time())}",
                    target_id=block.block_id,
                    provenance=self.metadata.name,
                    confidence=ConfidenceScore(score=confidence, method=method),
                    academic_type=academic_type,
                    reasoning=reasoning,
                )
                context.annotation_store.add(anno)
