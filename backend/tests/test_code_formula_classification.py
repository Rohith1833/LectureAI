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
    SemanticAnnotation,
)


class TestCodeFormulaClassification(unittest.TestCase):

    def test_code_formula_pipeline(self):
        """Verify E2E topological pipeline order, programming code snippet promotion, and LaTeX equation classification."""
        config = IntelligenceConfig()
        engine = IntelligenceEngine(config)

        # Mock modules
        feat_mod = FeatureExtractionModule()
        heading_mod = HeadingDetectionModule()
        lqn_mod = ListQuoteNoteDetectionModule()
        tc_mod = TableCaptionDetectionModule()
        cf_mod = CodeFormulaDetectionModule()

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
            # Code block (Courier monospace font, containing def and return keywords)
            BlockSchema(
                block_id="b_code",
                page_number=1,
                reading_order=2,
                block_type=BlockType.PARAGRAPH,
                font_family="CourierNew",
                font_size=10.0,
                text="def factorial(n):\n    if n <= 1:\n        return 1\n    return n * factorial(n - 1)",
                bounding_box=BoundingBox(x0=50.0, y0=130.0, x1=400.0, y1=200.0),
            ),
            # Equation block (starts and ends with $$)
            BlockSchema(
                block_id="b_equation",
                page_number=1,
                reading_order=3,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=10.0,
                text="$$\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}$$",
                bounding_box=BoundingBox(x0=50.0, y0=220.0, x1=500.0, y1=240.0),
            ),
        ]

        doc = DocumentExtractionResult(
            upload_id="test_cf_class",
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
            modules=[cf_mod, tc_mod, lqn_mod, heading_mod, feat_mod],
            upload_id="test_cf_class",
        )

        self.assertTrue(report.success)
        self.assertEqual(
            report.execution_order,
            [
                "FEATURE_EXTRACTION_MODULE",
                "HEADING_DETECTION_MODULE",
                "LIST_QUOTE_NOTE_DETECTION_MODULE",
                "TABLE_CAPTION_DETECTION_MODULE",
                "CODE_FORMULA_DETECTION_MODULE",
            ]
        )

        # Query semantic annotations
        store = context.annotation_store
        sem_annos = store.find_by_type(SemanticAnnotation)
        self.assertTrue(len(sem_annos) >= 2)

        # Check block type updates in-place
        block_types = {b.block_id: b.block_type for b in doc.blocks}
        self.assertEqual(block_types["b_code"], BlockType.CODE)
        self.assertEqual(block_types["b_equation"], BlockType.EQUATION)


if __name__ == "__main__":
    unittest.main()
