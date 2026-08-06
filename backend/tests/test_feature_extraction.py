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
    FeatureAnnotation,
    SemanticAnnotation,
)


class TestFeatureExtraction(unittest.TestCase):

    def test_feature_extraction_pipeline_and_features(self):
        """Verify E2E feature extraction math, spacing, context mapping, and cache hits."""
        config = IntelligenceConfig()
        engine = IntelligenceEngine(config)
        module = FeatureExtractionModule()

        # Build mock document extraction with two sequential blocks on same page
        pages = [PageSchema(page_number=1, width=600.0, height=800.0)]
        blocks = [
            BlockSchema(
                block_id="block_a",
                page_number=1,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=12.0,
                bold=True,
                italic=False,
                text="THIS IS AN ENTIRELY UPPERCASE HEADER BLOCK.",
                bounding_box=BoundingBox(x0=50.0, y0=100.0, x1=550.0, y1=130.0),
            ),
            BlockSchema(
                block_id="block_b",
                page_number=1,
                reading_order=2,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=10.0,
                bold=False,
                italic=True,
                text="This is a body paragraph following the header block. It contains some digits 12345.",
                bounding_box=BoundingBox(x0=50.0, y0=145.0, x1=500.0, y1=175.0),
            ),
        ]

        doc = DocumentExtractionResult(
            upload_id="test_feat_extract",
            status="processed",
            metadata=DocumentMetadataSchema(page_count=1),
            pages=pages,
            blocks=blocks,
            tables=[],
            images=[],
            extraction_timestamp="t",
            processing_time=0.0,
        )

        # 1. First Run: Execute extraction
        context, report = engine.execute(
            document=doc,
            page_metadata={1: pages[0]},
            document_metadata=doc.metadata,
            modules=[module],
            upload_id="test_feat_extract",
        )

        self.assertTrue(report.success)
        self.assertEqual(len(report.metrics), 1)
        self.assertTrue(report.metrics["FEATURE_EXTRACTION_MODULE"].success)

        # 2. Query AnnotationStore
        store = context.annotation_store
        annos = store.find_by_type(FeatureAnnotation)
        self.assertEqual(len(annos), 2)

        # Map by target block id
        anno_map = {a.target_id: a for a in annos}
        self.assertIn("block_a", anno_map)
        self.assertIn("block_b", anno_map)

        # 3. Assert Typography & Geometry Features
        feat_a = anno_map["block_a"].features
        self.assertEqual(feat_a.typography.font_family, "Arial")
        self.assertEqual(feat_a.typography.font_size, 12.0)
        self.assertTrue(feat_a.typography.bold)
        self.assertFalse(feat_a.typography.italic)
        self.assertTrue(feat_a.typography.is_all_caps)
        self.assertFalse(feat_a.typography.is_title_case)
        self.assertTrue(feat_a.typography.starts_with_capital)
        self.assertTrue(feat_a.typography.ends_with_punctuation)

        self.assertEqual(feat_a.geometry.width, 500.0)
        self.assertEqual(feat_a.geometry.height, 30.0)
        self.assertEqual(feat_a.geometry.margin_left, 50.0)
        self.assertEqual(feat_a.geometry.margin_right, 50.0)
        self.assertEqual(feat_a.geometry.alignment, "center")  # margin_l == margin_r

        # 4. Assert Layout Features (Paragraph Spacing Above/Below)
        feat_b = anno_map["block_b"].features
        # vertical spacing gap between block_a.y1 (130) and block_b.y0 (145) should be 15
        self.assertEqual(feat_b.layout.paragraph_spacing_above, 15.0)
        self.assertEqual(feat_a.layout.paragraph_spacing_below, 15.0)
        self.assertTrue(feat_a.layout.is_at_top)
        self.assertFalse(feat_a.layout.is_at_bottom)
        self.assertTrue(feat_b.layout.is_at_bottom)
        self.assertFalse(feat_b.layout.is_at_top)

        # 5. Assert Statistical Features
        self.assertEqual(feat_a.statistical.word_count, 7)
        self.assertEqual(feat_a.statistical.char_count, len(blocks[0].text))
        self.assertTrue(feat_a.statistical.uppercase_ratio > 0.8)
        self.assertEqual(feat_a.statistical.digit_ratio, 0.0)

        # block_b has digits
        self.assertTrue(feat_b.statistical.digit_ratio > 0.0)
        self.assertEqual(feat_b.statistical.word_count, 14)

        # 6. Assert Context Features
        self.assertEqual(feat_a.context.next_block_id, "block_b")
        self.assertEqual(feat_a.context.next_block_font_size, 10.0)
        self.assertIn("body paragraph", feat_a.context.next_block_text)

        self.assertEqual(feat_b.context.prev_block_id, "block_a")
        self.assertEqual(feat_b.context.prev_block_font_size, 12.0)
        self.assertIn("UPPERCASE", feat_b.context.prev_block_text)

        # 7. Second Run: Test Caching Speed
        # Clean the store to record only new runs, but keep module cached state
        context2, report2 = engine.execute(
            document=doc,
            page_metadata={1: pages[0]},
            document_metadata=doc.metadata,
            modules=[module],
            upload_id="test_feat_extract_run2",
        )
        self.assertTrue(report2.success)
        self.assertEqual(len(context2.annotation_store.find_by_type(FeatureAnnotation)), 2)

        # 8. Boundary Enforcement Assertions (No semantic classifications must occur)
        self.assertEqual(len(context2.annotation_store.find_by_type(SemanticAnnotation)), 0)


if __name__ == "__main__":
    unittest.main()
