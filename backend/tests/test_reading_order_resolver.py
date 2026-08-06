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
    ReadingOrderIntelligenceModule,
    ReadingOrderAnnotation,
)


class TestReadingOrderResolver(unittest.TestCase):

    def test_reading_order_two_columns(self):
        """Verify reading order sorting on dual column pages and in-place links propagation."""
        config = IntelligenceConfig()
        engine = IntelligenceEngine(config)

        # Mock modules
        feat_mod = FeatureExtractionModule()
        ro_mod = ReadingOrderIntelligenceModule()

        # Build mock document representing two-columns layout with a spanning title
        pages = [PageSchema(page_number=1, width=600.0, height=800.0)]
        blocks = [
            # 1. Left column block (initially index 0, but should be read after title)
            BlockSchema(
                block_id="b_left_1",
                page_number=1,
                reading_order=0,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=10.0,
                text="Left Column First Block text content goes here.",
                bounding_box=BoundingBox(x0=50.0, y0=140.0, x1=280.0, y1=180.0),
            ),
            # 2. Spanning title block (initially index 1, but should be read first)
            BlockSchema(
                block_id="b_title",
                page_number=1,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=16.0,
                text="SPANNING TITLE OF THE BOOK PAGE",
                bounding_box=BoundingBox(x0=50.0, y0=50.0, x1=550.0, y1=90.0),
            ),
            # 3. Right column block
            BlockSchema(
                block_id="b_right_1",
                page_number=1,
                reading_order=2,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=10.0,
                text="Right Column First Block text content goes here.",
                bounding_box=BoundingBox(x0=320.0, y0=140.0, x1=550.0, y1=180.0),
            ),
            # 4. Left column block 2
            BlockSchema(
                block_id="b_left_2",
                page_number=1,
                reading_order=3,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=10.0,
                text="Left Column Second Block text content.",
                bounding_box=BoundingBox(x0=50.0, y0=200.0, x1=280.0, y1=230.0),
            ),
            # 5. Right column block 2
            BlockSchema(
                block_id="b_right_2",
                page_number=1,
                reading_order=4,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=10.0,
                text="Right Column Second Block text.",
                bounding_box=BoundingBox(x0=320.0, y0=200.0, x1=550.0, y1=230.0),
            ),
        ]

        doc = DocumentExtractionResult(
            upload_id="test_ro_class",
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
            modules=[ro_mod, feat_mod],
            upload_id="test_ro_class",
        )

        self.assertTrue(report.success)
        self.assertEqual(
            report.execution_order,
            ["FEATURE_EXTRACTION_MODULE", "READING_ORDER_INTELLIGENCE_MODULE"]
        )

        # Verify in-place blocks reordering
        ordered_ids = [b.block_id for b in doc.blocks]
        self.assertEqual(
            ordered_ids,
            ["b_title", "b_left_1", "b_left_2", "b_right_1", "b_right_2"]
        )

        # Verify links are set correctly
        self.assertEqual(doc.blocks[0].previous_block_id, None)
        self.assertEqual(doc.blocks[0].next_block_id, "b_left_1")
        self.assertEqual(doc.blocks[1].previous_block_id, "b_title")
        self.assertEqual(doc.blocks[1].next_block_id, "b_left_2")
        self.assertEqual(doc.blocks[2].previous_block_id, "b_left_1")
        self.assertEqual(doc.blocks[2].next_block_id, "b_right_1")
        self.assertEqual(doc.blocks[3].previous_block_id, "b_left_2")
        self.assertEqual(doc.blocks[3].next_block_id, "b_right_2")
        self.assertEqual(doc.blocks[4].next_block_id, None)

        # Verify annotations in AnnotationStore
        store = context.annotation_store
        ro_annos = store.find_by_type(ReadingOrderAnnotation)
        self.assertEqual(len(ro_annos), 5)

        anno_map = {a.target_id: a for a in ro_annos}
        self.assertEqual(anno_map["b_title"].sequence_index, 0)
        self.assertEqual(anno_map["b_title"].column_index, 0)
        
        self.assertEqual(anno_map["b_left_1"].sequence_index, 1)
        self.assertEqual(anno_map["b_left_1"].column_index, 0)
        
        self.assertEqual(anno_map["b_left_2"].sequence_index, 2)
        self.assertEqual(anno_map["b_left_2"].column_index, 0)
        
        self.assertEqual(anno_map["b_right_1"].sequence_index, 3)
        self.assertEqual(anno_map["b_right_1"].column_index, 1)
        
        self.assertEqual(anno_map["b_right_2"].sequence_index, 4)
        self.assertEqual(anno_map["b_right_2"].column_index, 1)

        # Verify raw parser extraction order in extra_metadata
        # Initial blocks list in Test:
        # 0: b_left_1, 1: b_title, 2: b_right_1, 3: b_left_2, 4: b_right_2
        self.assertEqual(doc.blocks[0].extra_metadata["original_parser_order"], 1)  # b_title
        self.assertEqual(doc.blocks[1].extra_metadata["original_parser_order"], 0)  # b_left_1
        self.assertEqual(doc.blocks[2].extra_metadata["original_parser_order"], 3)  # b_left_2
        self.assertEqual(doc.blocks[3].extra_metadata["original_parser_order"], 2)  # b_right_1
        self.assertEqual(doc.blocks[4].extra_metadata["original_parser_order"], 4)  # b_right_2


if __name__ == "__main__":
    unittest.main()
