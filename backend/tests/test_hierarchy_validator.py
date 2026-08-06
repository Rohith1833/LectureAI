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
    QualityAnnotation,
)


class TestHierarchyValidator(unittest.TestCase):

    def test_hierarchy_validation_metrics(self):
        """Verify orphan block detection, heading jumps warnings, and IntelligenceReport metrics population."""
        config = IntelligenceConfig()
        engine = IntelligenceEngine(config)

        # Mock modules sequence
        feat_mod = FeatureExtractionModule()
        heading_mod = HeadingDetectionModule()
        lqn_mod = ListQuoteNoteDetectionModule()
        tc_mod = TableCaptionDetectionModule()
        cf_mod = CodeFormulaDetectionModule()
        ro_mod = ReadingOrderIntelligenceModule()
        hb_mod = HierarchyBuilderModule()
        hv_mod = HierarchyValidationModule()

        # Build mock document containing:
        # - H1 Chapter Heading
        # - Paragraph 1 (under H1)
        # - H3 Heading (Nesting jump H1 -> H3!)
        # - Paragraph 2 (under H3)
        # - Paragraph 3 (Orphan block: placed on top of page before any heading!)
        pages = [PageSchema(page_number=1, width=600.0, height=800.0)]
        blocks = [
            # Orphan paragraph (placed before any heading)
            BlockSchema(
                block_id="b_orphan",
                page_number=1,
                reading_order=0,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=10.0,
                text="Orphan paragraph before chapter heading start.",
                bounding_box=BoundingBox(x0=50.0, y0=30.0, x1=500.0, y1=45.0),
            ),
            # H1 Heading
            BlockSchema(
                block_id="b_h1",
                page_number=1,
                reading_order=1,
                block_type=BlockType.HEADING,
                heading_level=1,
                font_family="Arial",
                font_size=20.0,
                bold=True,
                text="Chapter 1: The Beginnings",
                bounding_box=BoundingBox(x0=50.0, y0=60.0, x1=300.0, y1=85.0),
            ),
            # H3 Heading (represents a skipped level jump from H1)
            BlockSchema(
                block_id="b_h3",
                page_number=1,
                reading_order=2,
                block_type=BlockType.HEADING,
                heading_level=3,
                font_family="Arial",
                font_size=14.0,
                bold=True,
                text="1.1.1 Skipping H2",
                bounding_box=BoundingBox(x0=50.0, y0=100.0, x1=300.0, y1=120.0),
            ),
            # Paragraph under H3
            BlockSchema(
                block_id="b_para",
                page_number=1,
                reading_order=3,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=10.0,
                text="Paragraph under subsection.",
                bounding_box=BoundingBox(x0=50.0, y0=130.0, x1=400.0, y1=150.0),
            ),
            # H2 Heading placed at the end to register size 16.0 heading size
            BlockSchema(
                block_id="b_h2",
                page_number=1,
                reading_order=4,
                block_type=BlockType.HEADING,
                heading_level=2,
                font_family="Arial",
                font_size=16.0,
                bold=True,
                text="1.1 Another Section",
                bounding_box=BoundingBox(x0=50.0, y0=180.0, x1=300.0, y1=205.0),
            ),
        ]

        doc = DocumentExtractionResult(
            upload_id="test_hv_class",
            status="processed",
            metadata=DocumentMetadataSchema(page_count=1),
            pages=pages,
            blocks=blocks,
            tables=[],
            images=[],
            extraction_timestamp="t",
            processing_time=0.0,
        )

        # Run full pipeline sequence
        context, report = engine.execute(
            document=doc,
            page_metadata={1: pages[0]},
            document_metadata=doc.metadata,
            modules=[hv_mod, hb_mod, ro_mod, cf_mod, tc_mod, lqn_mod, heading_mod, feat_mod],
            upload_id="test_hv_class",
        )

        self.assertTrue(report.success)
        self.assertEqual(
            report.execution_order[-2:],
            ["HIERARCHY_BUILDER_MODULE", "HIERARCHY_VALIDATION_MODULE"]
        )

        # Verify IntelligenceReport fields extended correctly
        self.assertEqual(report.hierarchy_depth, 2)
        self.assertEqual(report.total_sections, 3)  # b_h1, b_h3, and b_h2
        self.assertEqual(report.orphan_count, 1)    # b_orphan
        self.assertEqual(report.root_count, 2)      # b_orphan and b_h1 (parent_id is None)
        self.assertTrue(report.hierarchy_consistency_score < 1.0)
        self.assertEqual(report.graph_statistics["total_nodes"], 5)

        # Check Module warnings list
        val_metrics = report.metrics["HIERARCHY_VALIDATION_MODULE"]
        self.assertTrue(len(val_metrics.warnings) >= 2)
        warnings_str = "".join(val_metrics.warnings)
        self.assertIn("Orphan block of type", warnings_str)
        self.assertIn("Heading level jump from H1 to H3", warnings_str)

        # Query QualityAnnotation from store
        store = context.annotation_store
        q_annos = store.find_by_type(QualityAnnotation)
        self.assertEqual(len(q_annos), 1)
        self.assertEqual(q_annos[0].metadata["orphan_count"], 1)
        self.assertEqual(q_annos[0].metadata["max_depth"], 2)


if __name__ == "__main__":
    unittest.main()
