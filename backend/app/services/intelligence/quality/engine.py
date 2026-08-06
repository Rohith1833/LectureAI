import time
import math
from typing import Dict, List, Any
from app.schemas.document import BlockSchema
from app.services.intelligence.base import BaseIntelligenceModule, ModuleMetadata
from app.services.intelligence.context import IntelligenceContext
from app.services.intelligence.annotations import ConfidenceScore, QualityAnnotation
from app.services.intelligence.quality.evaluators import (
    OCRQualityEvaluator,
    LayoutQualityEvaluator,
    SemanticQualityEvaluator,
    HierarchyQualityEvaluator,
    ReadingQualityEvaluator,
)
from app.services.intelligence.events import (
    QualityAnalysisStarted,
    OCRQualityEvaluated,
    StructuralQualityEvaluated,
    SemanticQualityEvaluated,
    DocumentQualityCompleted,
)


class DocumentQualityModule(BaseIntelligenceModule):
    """Orchestrates document validation metrics, scores OCR spelling, layout blocks, and reading order ambiguity."""

    def __init__(self):
        self._metadata = ModuleMetadata(
            name="DOCUMENT_QUALITY_MODULE",
            version="1.0.0",
            author="LectureAI Core",
            stage="document_validation",
            priority=120,
            dependencies=[
                "FEATURE_EXTRACTION_MODULE",
                "HEADING_DETECTION_MODULE",
                "LIST_QUOTE_NOTE_DETECTION_MODULE",
                "TABLE_CAPTION_DETECTION_MODULE",
                "CODE_FORMULA_DETECTION_MODULE",
                "READING_ORDER_INTELLIGENCE_MODULE",
                "HIERARCHY_BUILDER_MODULE",
                "HIERARCHY_VALIDATION_MODULE",
            ],
            enabled=True,
        )
        self.evaluators = [
            OCRQualityEvaluator(),
            LayoutQualityEvaluator(),
            SemanticQualityEvaluator(),
            HierarchyQualityEvaluator(),
            ReadingQualityEvaluator(),
        ]

    @property
    def metadata(self) -> ModuleMetadata:
        return self._metadata

    def initialize(self, config: dict) -> None:
        pass

    def execute(self, context: IntelligenceContext) -> None:
        doc = context.document
        if not doc:
            return

        # Publish event: QualityAnalysisStarted
        context.event_publisher.publish(QualityAnalysisStarted(upload_id=doc.upload_id))

        results = {}
        all_warnings = []
        all_recs = []

        # Run evaluators sequentially
        for evaluator in self.evaluators:
            res = evaluator.evaluate(context)
            results[evaluator.name] = res["score"]
            all_warnings.extend(res.get("warnings", []))
            all_recs.extend(res.get("recommendations", []))

            # Publish fine-grained evaluation events
            if evaluator.name == "ocr_quality":
                context.event_publisher.publish(OCRQualityEvaluated(upload_id=doc.upload_id, ocr_score=res["score"]))
            elif evaluator.name == "layout_quality":
                context.event_publisher.publish(StructuralQualityEvaluated(upload_id=doc.upload_id, structural_score=res["score"]))
            elif evaluator.name == "semantic_quality":
                context.event_publisher.publish(SemanticQualityEvaluated(upload_id=doc.upload_id, semantic_score=res["score"]))

        # Extract sub-scores
        s_ocr = results.get("ocr_quality", 1.0)
        s_layout = results.get("layout_quality", 1.0)
        s_semantic = results.get("semantic_quality", 1.0)
        s_hierarchy = results.get("hierarchy_quality", 1.0)
        s_reading = results.get("reading_quality", 1.0)

        # 100% deterministic Overall Score (Geometric mean calculation)
        s_overall = math.pow(s_ocr * s_layout * s_semantic * s_hierarchy * s_reading, 0.20)
        s_overall = max(0.0, min(1.0, s_overall))

        # Compile global recommendations based on the overall document state
        if s_overall < 0.60:
            all_recs.append({
                "recommendation_code": "LOW_CONFIDENCE_FOR_AI",
                "severity": "CRITICAL",
                "message": f"Document quality score is critical ({s_overall:.2f}); automated AI processing reliability is low.",
                "target_id": doc.upload_id,
            })
        elif s_overall >= 0.85:
            all_recs.append({
                "recommendation_code": "SUITABLE_FOR_GENERATION",
                "severity": "INFO",
                "message": "High reliability document layout detected. Suitable for direct RAG and lecture generation.",
                "target_id": doc.upload_id,
            })

        # Hierarchy / Reading / Spacing recommendation cascade
        if s_hierarchy < 0.60 or s_reading < 0.60 or s_layout < 0.70:
            # Check if recommendation is already added
            if not any(r["recommendation_code"] == "MANUAL_REVIEW_REQUIRED" for r in all_recs):
                all_recs.append({
                    "recommendation_code": "MANUAL_REVIEW_REQUIRED",
                    "severity": "WARNING",
                    "message": "Inconsistent structure and column ambiguities detected. Manual review is required.",
                    "target_id": doc.upload_id,
                })

        # Save extended QualityAnnotation
        quality_anno = QualityAnnotation(
            annotation_id=f"doc_q_{doc.upload_id}_{int(time.time())}",
            target_id=doc.upload_id,
            provenance=self.metadata.name,
            confidence=ConfidenceScore(
                score=s_overall,
                contributors={
                    "ocr_quality": s_ocr,
                    "layout_quality": s_layout,
                    "semantic_quality": s_semantic,
                    "hierarchy_quality": s_hierarchy,
                    "reading_quality": s_reading,
                },
                method="geometric_quality_aggregation",
            ),
            is_scanned=context.shared_cache.get("is_scanned", False),
            ocr_confidence_raw=s_ocr,
            ocr_quality_score=s_ocr,
            layout_quality_score=s_layout,
            semantic_quality_score=s_semantic,
            hierarchy_quality_score=s_hierarchy,
            reading_quality_score=s_reading,
            overall_quality_score=s_overall,
            metadata={
                "warnings": all_warnings,
                "recommendations": all_recs,
            }
        )
        context.annotation_store.add(quality_anno)

        # Store warnings in context diagnostics list
        for w in all_warnings:
            context.diagnostics.append({
                "module": self.metadata.name,
                "warning": f"[{w['warning_code']}] {w['message']}"
            })

        # Publish event: DocumentQualityCompleted
        context.event_publisher.publish(
            DocumentQualityCompleted(
                upload_id=doc.upload_id,
                overall_score=s_overall,
                warning_count=len(all_warnings),
            )
        )
