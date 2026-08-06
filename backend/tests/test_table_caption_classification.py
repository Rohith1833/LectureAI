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
    SemanticAnnotation,
)


class TestTableCaptionClassification(unittest.TestCase):

    def test_table_caption_pipeline(self):
        """Verify E2E topological pipeline order, table detection, and caption prefix matching."""
        config = IntelligenceConfig()
        engine = IntelligenceEngine(config)

        # Mock modules
        feat_mod = FeatureExtractionModule()
        heading_mod = HeadingDetectionModule()
        lqn_mod = ListQuoteNoteDetectionModule()
        tc_mod = TableCaptionDetectionModule()

        # Build mock document
        pages = [PageSchema(page_number=1, width=600.0, height=800.0)]
        blocks = [
            # dominant body paragraph
            BlockSchema(
                block_id="b_body",
                page_number=1,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=10.0,
                text="This is standard body paragraph text used to baseline statistics.",
                bounding_box=BoundingBox(x0=50.0, y0=100.0, x1=550.0, y1=120.0),
            ),
            # Table block (3 lines, containing tab column separators)
            BlockSchema(
                block_id="b_table",
                page_number=1,
                reading_order=2,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=10.0,
                text="Year      Revenue   Growth\n2024      $100K     12%\n2025      $140K     40%",
                bounding_box=BoundingBox(x0=50.0, y0=130.0, x1=400.0, y1=180.0),
            ),
            # Figure caption block
            BlockSchema(
                block_id="b_caption",
                page_number=1,
                reading_order=3,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=9.0,
                text="Figure 14.1: Flow diagram representing the normalization stages.",
                bounding_box=BoundingBox(x0=50.0, y0=190.0, x1=500.0, y1=205.0),
            ),
        ]

        doc = DocumentExtractionResult(
            upload_id="test_tc_class",
            status="processed",
            metadata=DocumentMetadataSchema(page_count=1),
            pages=pages,
            blocks=blocks,
            tables=[],
            images=[],
            extraction_timestamp="t",
            processing_time=0.0,
        )

        # Run pipeline
        context, report = engine.execute(
            document=doc,
            page_metadata={1: pages[0]},
            document_metadata=doc.metadata,
            modules=[tc_mod, lqn_mod, heading_mod, feat_mod],
            upload_id="test_tc_class",
        )

        self.assertTrue(report.success)
        self.assertEqual(
            report.execution_order,
            [
                "FEATURE_EXTRACTION_MODULE",
                "HEADING_DETECTION_MODULE",
                "LIST_QUOTE_NOTE_DETECTION_MODULE",
                "TABLE_CAPTION_DETECTION_MODULE",
            ]
        )

        # Query semantic annotations
        store = context.annotation_store
        sem_annos = store.find_by_type(SemanticAnnotation)
        self.assertTrue(len(sem_annos) >= 2)

        # Check block type updates in-place
        block_types = {b.block_id: b.block_type for b in doc.blocks}
        self.assertEqual(block_types["b_table"], BlockType.TABLE)
        self.assertEqual(block_types["b_caption"], BlockType.CAPTION)

        # Boundary checks
        for block in doc.blocks:
            self.assertNotIn(block.block_type, [BlockType.IMAGE, BlockType.EQUATION])


if __name__ == "__main__":
    unittest.main()
