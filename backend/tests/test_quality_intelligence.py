import unittest
from typing import List

from app.schemas.document import (
    DocumentExtractionResult,
    DocumentMetadataSchema,
    PageSchema,
    BlockSchema,
    BlockType,
    BoundingBox,
)
from app.services.intelligence import (
    IntelligenceConfig,
    IntelligenceEngine,
    FeatureExtractionModule,
    HeadingDetectionModule,
    ListQuoteNoteDetectionModule,
    TableCaptionDetectionModule,
    CodeFormulaDetectionModule,
    ReadingOrderIntelligenceModule,
    HierarchyBuilderModule,
    HierarchyValidationModule,
    DocumentQualityModule,
    QualityAnnotation,
)


class TestQualityIntelligence(unittest.TestCase):

    def test_quality_intelligence_pipeline(self):
        """Verify quality evaluators calculations, recommendations list, warnings structure, and telemetry."""
        config = IntelligenceConfig()
        engine = IntelligenceEngine(config)

        # Full modules list including the new DOCUMENT_QUALITY_MODULE
        feat_mod = FeatureExtractionModule()
        heading_mod = HeadingDetectionModule()
        lqn_mod = ListQuoteNoteDetectionModule()
        tc_mod = TableCaptionDetectionModule()
        cf_mod = CodeFormulaDetectionModule()
        ro_mod = ReadingOrderIntelligenceModule()
        hb_mod = HierarchyBuilderModule()
        hv_mod = HierarchyValidationModule()
        q_mod = DocumentQualityModule()

        # Build mock document representing layout/spelling quality:
        # - Block 1: H1 Heading (clean text, bold)
        # - Block 2: Paragraph with suspicious words and garbage control characters
        # - Block 3: Empty layout block (Layout penalty)
        # - Block 4: Overlapping layout block (Layout overlap penalty)
        pages = [PageSchema(page_number=1, width=600.0, height=800.0)]
        blocks = [
            BlockSchema(
                block_id="b_h1",
                page_number=1,
                reading_order=0,
                block_type=BlockType.HEADING,
                heading_level=1,
                font_family="Arial",
                font_size=20.0,
                bold=True,
                text="Chapter 1: Mathematical Structures",
                bounding_box=BoundingBox(x0=50.0, y0=50.0, x1=400.0, y1=85.0),
            ),
            # Low quality OCR text block
            BlockSchema(
                block_id="b_ocr_noise",
                page_number=1,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=10.0,
                confidence=0.40,  # Low raw confidence
                text="The equat1on holds for bcdfgh elements \x00\x07.",
                bounding_box=BoundingBox(x0=50.0, y0=100.0, x1=550.0, y1=120.0),
            ),
            # Empty block
            BlockSchema(
                block_id="b_empty",
                page_number=1,
                reading_order=2,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=10.0,
                text="   ",
                bounding_box=BoundingBox(x0=50.0, y0=140.0, x1=150.0, y1=155.0),
            ),
            # Overlapping block
            BlockSchema(
                block_id="b_overlap",
                page_number=1,
                reading_order=3,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=10.0,
                confidence=0.50,  # Low raw confidence
                text="This text intersects coordinates with the previous block.",
                bounding_box=BoundingBox(x0=50.0, y0=130.0, x1=200.0, y1=150.0), # Intersects b_empty
            ),
        ]

        doc = DocumentExtractionResult(
            upload_id="test_quality_upload",
            status="processed",
            metadata=DocumentMetadataSchema(page_count=1),
            pages=pages,
            blocks=blocks,
            tables=[],
            images=[],
            extraction_timestamp="t",
            processing_time=0.0,
        )

        # Run pipeline E2E
        context, report = engine.execute(
            document=doc,
            page_metadata={1: pages[0]},
            document_metadata=doc.metadata,
            modules=[q_mod, hv_mod, hb_mod, ro_mod, cf_mod, tc_mod, lqn_mod, heading_mod, feat_mod],
            upload_id="test_quality_upload",
        )

        self.assertTrue(report.success)
        self.assertEqual(report.execution_order[-1], "DOCUMENT_QUALITY_MODULE")

        # 1. Assert telemetry score fields populated on report
        self.assertIsNotNone(report.ocr_quality_score)
        self.assertIsNotNone(report.layout_quality_score)
        self.assertIsNotNone(report.semantic_quality_score)
        self.assertIsNotNone(report.hierarchy_quality_score)
        self.assertIsNotNone(report.reading_quality_score)
        self.assertIsNotNone(report.overall_quality_score)

        # Confirm overall score is the geometric mean product
        expected_overall = (
            report.ocr_quality_score *
            report.layout_quality_score *
            report.semantic_quality_score *
            report.hierarchy_quality_score *
            report.reading_quality_score
        ) ** 0.20
        self.assertAlmostEqual(report.overall_quality_score, expected_overall, places=4)

        # 2. Confirm warnings generated and mapped
        self.assertTrue(len(report.quality_warnings) > 0)
        warning_codes = [w["warning_code"] for w in report.quality_warnings]
        self.assertIn("POOR_OCR_CONFIDENCE", warning_codes)
        self.assertIn("OVERLAPPING_LAYOUT_ELEMENTS", warning_codes)

        # 3. Confirm recommendations list generated
        self.assertTrue(len(report.processing_recommendations) > 0)
        rec_codes = [r["recommendation_code"] for r in report.processing_recommendations]
        self.assertIn("RERUN_OCR_RECOMMENDED", rec_codes)

        # 4. Check store persistence
        q_annos = context.annotation_store.find_by_type(QualityAnnotation)
        # We should find two QualityAnnotations (one from validation, one from quality_engine)
        self.assertEqual(len(q_annos), 2)
        doc_q_anno = next(q for q in q_annos if q.provenance == "DOCUMENT_QUALITY_MODULE")
        self.assertEqual(doc_q_anno.ocr_quality_score, report.ocr_quality_score)
        self.assertEqual(doc_q_anno.overall_quality_score, report.overall_quality_score)


if __name__ == "__main__":
    unittest.main()
