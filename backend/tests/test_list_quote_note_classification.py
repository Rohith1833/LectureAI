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
    SemanticAnnotation,
)


class TestListQuoteNoteClassification(unittest.TestCase):

    def test_list_quote_note_pipeline(self):
        """Verify topological resolution order, classifications of lists/quotes/notes, and in-place updates."""
        config = IntelligenceConfig()
        engine = IntelligenceEngine(config)

        # Mock modules
        feat_mod = FeatureExtractionModule()
        heading_mod = HeadingDetectionModule()
        lqn_mod = ListQuoteNoteDetectionModule()

        # Build mock document
        pages = [PageSchema(page_number=1, width=600.0, height=800.0)]
        blocks = [
            # dominant body size paragraph (dominant = 10.0, based on length)
            BlockSchema(
                block_id="b_body",
                page_number=1,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=10.0,
                text="This represents the dominant text size body block which serves as the statistical baseline.",
                bounding_box=BoundingBox(x0=50.0, y0=100.0, x1=550.0, y1=120.0),
            ),
            # list bullet
            BlockSchema(
                block_id="b_list_bullet",
                page_number=1,
                reading_order=2,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=10.0,
                text="• This is a bulleted list item",
                bounding_box=BoundingBox(x0=50.0, y0=130.0, x1=300.0, y1=145.0),
            ),
            # list decimal
            BlockSchema(
                block_id="b_list_num",
                page_number=1,
                reading_order=3,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=10.0,
                text="2.3) A numbered list item",
                bounding_box=BoundingBox(x0=50.0, y0=155.0, x1=300.0, y1=170.0),
            ),
            # quote by quote marks wrap
            BlockSchema(
                block_id="b_quote_marks",
                page_number=1,
                reading_order=4,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=10.0,
                text='“This is a quoted blockquote passage.”',
                bounding_box=BoundingBox(x0=50.0, y0=180.0, x1=400.0, y1=195.0),
            ),
            # quote by indentation margin (dominant margin left/right is 50.0)
            BlockSchema(
                block_id="b_quote_indent",
                page_number=1,
                reading_order=5,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=10.0,
                text='An indented quote block text with wider margins than dominant layout.',
                bounding_box=BoundingBox(x0=80.0, y0=205.0, x1=450.0, y1=220.0),
            ),
            # note keyword
            BlockSchema(
                block_id="b_note",
                page_number=1,
                reading_order=6,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=10.0,
                text="Note: This is a warning tip box.",
                bounding_box=BoundingBox(x0=50.0, y0=230.0, x1=400.0, y1=245.0),
            ),
            # footnote at bottom page margin (position y = 760/800 = 0.95, size = 8.0, starts with digit)
            BlockSchema(
                block_id="b_footnote",
                page_number=1,
                reading_order=7,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=8.0,
                text="1 Crucial bottom citation text.",
                bounding_box=BoundingBox(x0=50.0, y0=760.0, x1=300.0, y1=775.0),
            ),
        ]

        doc = DocumentExtractionResult(
            upload_id="test_lqn_class",
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
            modules=[lqn_mod, heading_mod, feat_mod],
            upload_id="test_lqn_class",
        )

        self.assertTrue(report.success)
        self.assertEqual(
            report.execution_order,
            ["FEATURE_EXTRACTION_MODULE", "HEADING_DETECTION_MODULE", "LIST_QUOTE_NOTE_DETECTION_MODULE"]
        )

        # Query semantic annotations from store
        store = context.annotation_store
        sem_annos = store.find_by_type(SemanticAnnotation)
        # 7 blocks total. b_body is paragraph, others classified by LQN
        self.assertTrue(len(sem_annos) >= 6)

        # Map targets
        block_types = {b.block_id: b.block_type for b in doc.blocks}

        # 1. Assert List Classifications
        self.assertEqual(block_types["b_list_bullet"], BlockType.LIST)
        self.assertEqual(block_types["b_list_num"], BlockType.LIST)

        # 2. Assert Quote Classifications
        self.assertEqual(block_types["b_quote_marks"], BlockType.QUOTE)
        self.assertEqual(block_types["b_quote_indent"], BlockType.QUOTE)

        # 3. Assert Note/Footnote Classifications
        self.assertEqual(block_types["b_note"], BlockType.NOTE)
        self.assertEqual(block_types["b_footnote"], BlockType.FOOTNOTE)

        # 4. Milestone Boundaries Assertion
        # We assert that tables, captions, formulas, or code detections are NEVER performed.
        for block in doc.blocks:
            self.assertNotIn(block.block_type, [BlockType.TABLE, BlockType.CAPTION, BlockType.IMAGE])


if __name__ == "__main__":
    unittest.main()
