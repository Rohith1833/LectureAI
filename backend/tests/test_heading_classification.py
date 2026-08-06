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
    SemanticAnnotation,
    BlockFeatures,
    ConfidenceScore,
)


class TestHeadingClassification(unittest.TestCase):

    def test_heading_classification_pipeline(self):
        """Verify topological execution sequence, E2E scoring metrics, and in-place block updates."""
        config = IntelligenceConfig()
        engine = IntelligenceEngine(config)
        
        # Instantiate modules
        feat_mod = FeatureExtractionModule()
        heading_mod = HeadingDetectionModule()
        
        # Mock document blocks:
        # - Block 1: H1 (size 24.0, bold, uppercase, centered, gap below = 30)
        # - Block 2: Paragraph (size 10.0, dominant, standard length, sentence ender, gap above = 30)
        # - Block 3: H2 (size 16.0, bold, Title Case, short)
        # - Block 4: Empty / Junk (low size, odd characters -> UNKNOWN)
        pages = [PageSchema(page_number=1, width=600.0, height=800.0)]
        blocks = [
            BlockSchema(
                block_id="b1",
                page_number=1,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,  # Initial state
                font_family="Times",
                font_size=24.0,
                bold=True,
                italic=False,
                text="CHAPTER 1: THE ROAD AHEAD",
                bounding_box=BoundingBox(x0=100.0, y0=50.0, x1=500.0, y1=80.0),
            ),
            BlockSchema(
                block_id="b2",
                page_number=1,
                reading_order=2,
                block_type=BlockType.PARAGRAPH,
                font_family="Times",
                font_size=10.0,
                bold=False,
                italic=False,
                text="This is a simple paragraph detailing the initial introductory content of the book. It must not be elevated.",
                bounding_box=BoundingBox(x0=50.0, y0=110.0, x1=550.0, y1=140.0),
            ),
            BlockSchema(
                block_id="b3",
                page_number=1,
                reading_order=3,
                block_type=BlockType.PARAGRAPH,
                font_family="Times",
                font_size=16.0,
                bold=True,
                italic=False,
                text="Section 1.1: Background History",
                bounding_box=BoundingBox(x0=50.0, y0=160.0, x1=350.0, y1=180.0),
            ),
            BlockSchema(
                block_id="b4",
                page_number=1,
                reading_order=4,
                block_type=BlockType.PARAGRAPH,
                font_family="Times",
                font_size=6.0,
                bold=False,
                italic=True,
                text="$$ * @",
                bounding_box=BoundingBox(x0=50.0, y0=200.0, x1=100.0, y1=210.0),
            ),
        ]

        doc = DocumentExtractionResult(
            upload_id="test_heading_class",
            status="processed",
            metadata=DocumentMetadataSchema(page_count=1),
            pages=pages,
            blocks=blocks,
            tables=[],
            images=[],
            extraction_timestamp="t",
            processing_time=0.0,
        )

        # Execute E2E Pipeline (resolution will sort: FEATURE_EXTRACTION_MODULE first, then HEADING_DETECTION_MODULE)
        context, report = engine.execute(
            document=doc,
            page_metadata={1: pages[0]},
            document_metadata=doc.metadata,
            modules=[heading_mod, feat_mod],  # Register in scrambled order to test topological sorting resolution
            upload_id="test_heading_class",
        )

        self.assertTrue(report.success)
        self.assertEqual(report.execution_order, ["FEATURE_EXTRACTION_MODULE", "HEADING_DETECTION_MODULE"])

        # Query SemanticAnnotations
        store = context.annotation_store
        sem_annos = store.find_by_type(SemanticAnnotation)
        self.assertEqual(len(sem_annos), 4)

        anno_map = {a.target_id: a for a in sem_annos}

        # 1. Assert Block Promotions
        # b1: heading level H1 (unique sizes: 24.0, 16.0 -> 24.0 is largest -> H1)
        self.assertEqual(doc.blocks[0].block_type, BlockType.HEADING)
        self.assertEqual(doc.blocks[0].heading_level, 1)
        self.assertEqual(anno_map["b1"].assigned_type, BlockType.HEADING)
        self.assertEqual(anno_map["b1"].metadata.get("heading_level"), 1)
        self.assertTrue(anno_map["b1"].confidence.score > 0.7)

        # b2: remains body PARAGRAPH
        self.assertEqual(doc.blocks[1].block_type, BlockType.PARAGRAPH)
        self.assertEqual(doc.blocks[1].heading_level, None)
        self.assertEqual(anno_map["b2"].assigned_type, BlockType.PARAGRAPH)

        # b3: heading level H2 (16.0 is second size -> H2)
        self.assertEqual(doc.blocks[2].block_type, BlockType.HEADING)
        self.assertEqual(doc.blocks[2].heading_level, 2)
        self.assertEqual(anno_map["b3"].assigned_type, BlockType.HEADING)
        self.assertEqual(anno_map["b3"].metadata.get("heading_level"), 2)

        # b4: low confidence falls back to UNKNOWN
        self.assertEqual(doc.blocks[3].block_type, BlockType.UNKNOWN)
        self.assertEqual(anno_map["b4"].assigned_type, BlockType.UNKNOWN)

        # 2. Check Reasoning details inside Annotation metadata
        b1_conf = anno_map["b1"].confidence
        self.assertIn("size", b1_conf.contributors)
        self.assertIn("bold", b1_conf.contributors)
        self.assertIn("length", b1_conf.contributors)
        self.assertEqual(b1_conf.method, "weighted_signals")

        # 3. Milestone Boundaries Assertion
        # We assert that lists, tables, captions, quotes, formulas, or code detections are NEVER performed.
        for block in doc.blocks:
            self.assertNotIn(block.block_type, [BlockType.LIST, BlockType.TABLE, BlockType.CAPTION])


if __name__ == "__main__":
    unittest.main()
