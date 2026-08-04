import os
import shutil
import unittest
from typing import List, Dict, Any
from unittest.mock import MagicMock

from app.schemas.document import (
    DocumentExtractionResult,
    DocumentMetadataSchema,
    PageSchema,
    BlockSchema,
    BlockType,
    BoundingBox,
)
from app.services.ocr.base_engine import BaseOCREngine
from app.services.ocr.page_detector import PageDetector, OCRStrategy
from app.services.ocr.layout_builder import OCRLayoutBuilder
from app.services.ocr.confidence import OCRConfidenceCalculator
from app.agents.ocr_agent import OCRAgent, merge_native_and_ocr_blocks, OCR_CACHE_DIR


class MockOCREngine(BaseOCREngine):
    """Test-specific mock OCR engine that simulates Tesseract outputs."""

    def __init__(self, mock_words: List[Dict[str, Any]] = None):
        self.mock_words = mock_words or [
            {
                "text": "Chapter",
                "bbox": (50, 100, 100, 120),
                "confidence": 0.95,
                "block_num": 1,
                "line_num": 1,
            },
            {
                "text": "1",
                "bbox": (110, 100, 130, 120),
                "confidence": 0.98,
                "block_num": 1,
                "line_num": 1,
            },
            {
                "text": "Introduction",
                "bbox": (140, 100, 250, 120),
                "confidence": 0.99,
                "block_num": 1,
                "line_num": 1,
            },
        ]

    def get_name(self) -> str:
        return "mock-tesseract"

    def get_version(self) -> str:
        return "5.0.0-mock"

    def is_available(self) -> bool:
        return True

    def perform_ocr(self, image_path: str) -> List[Dict[str, Any]]:
        return self.mock_words


class TestOCREngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a mock PDF file for testing pipeline runs
        cls.pdf_path = os.path.abspath("test_ocr_document.pdf")
        import fitz

        doc = fitz.open()
        # Page 1: Has digital text (Rich)
        page1 = doc.new_page(width=595, height=842)
        page1.insert_text((50, 100), "This is a rich digital page with plenty of characters to skip OCR.", fontsize=12)

        # Page 2: Has very sparse digital text (Scanned layer)
        page2 = doc.new_page(width=595, height=842)
        page2.insert_text((50, 100), "Sparse", fontsize=12)

        doc.save(cls.pdf_path)
        doc.close()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.pdf_path):
            os.remove(cls.pdf_path)
        # Clear cache for test page hashes
        if os.path.exists(OCR_CACHE_DIR):
            for f in os.listdir(OCR_CACHE_DIR):
                if f.endswith(".json"):
                    try:
                        os.remove(os.path.join(OCR_CACHE_DIR, f))
                    except Exception:
                        pass

    def test_page_detector_strategies(self):
        """Verify AUTO, FORCE, and SKIP rules of PageDetector."""
        detector = PageDetector(char_threshold=50)

        # Mock rich native block list (character length = 66)
        rich_blocks = [
            BlockSchema(
                block_id="1",
                page_number=1,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                text="This is a rich digital page with plenty of characters to skip OCR.",
                bounding_box=BoundingBox(x0=50, y0=100, x1=500, y1=120),
                font_size=12.0,
                bold=False,
                italic=False,
                confidence=1.0,
            )
        ]

        # Mock sparse native block list (character length = 6)
        sparse_blocks = [
            BlockSchema(
                block_id="2",
                page_number=2,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                text="Sparse",
                bounding_box=BoundingBox(x0=50, y0=100, x1=100, y1=120),
                font_size=12.0,
                bold=False,
                italic=False,
                confidence=1.0,
            )
        ]

        # AUTO Strategy
        self.assertFalse(detector.evaluate_page(1, rich_blocks, OCRStrategy.AUTO))
        self.assertTrue(detector.evaluate_page(2, sparse_blocks, OCRStrategy.AUTO))

        # FORCE Strategy
        self.assertTrue(detector.evaluate_page(1, rich_blocks, OCRStrategy.FORCE))
        self.assertTrue(detector.evaluate_page(2, sparse_blocks, OCRStrategy.FORCE))

        # SKIP Strategy
        self.assertFalse(detector.evaluate_page(1, rich_blocks, OCRStrategy.SKIP))
        self.assertFalse(detector.evaluate_page(2, sparse_blocks, OCRStrategy.SKIP))

    def test_merge_native_and_ocr_blocks(self):
        """Verify that overlapping blocks are filtered by confidence and non-overlapping are kept."""
        native = [
            BlockSchema(
                block_id="native-1",
                page_number=1,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                text="Native Overlapping Text",
                bounding_box=BoundingBox(x0=50, y0=100, x1=200, y1=150),
                confidence=0.80,  # lower confidence
                provenance="NATIVE",
            )
        ]

        ocr = [
            BlockSchema(
                block_id="ocr-1",
                page_number=1,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                text="OCR Higher Conf Text",
                bounding_box=BoundingBox(x0=55, y0=102, x1=198, y1=148),  # overlaps > 40%
                confidence=0.95,  # higher confidence
                provenance="OCR",
            ),
            BlockSchema(
                block_id="ocr-2",
                page_number=1,
                reading_order=2,
                block_type=BlockType.PARAGRAPH,
                text="OCR Non Overlapping",
                bounding_box=BoundingBox(x0=50, y0=300, x1=200, y1=350),  # no overlap
                confidence=0.90,
                provenance="OCR",
            ),
        ]

        merged = merge_native_and_ocr_blocks(native, ocr)

        # Assert duplicate was removed, keeping OCR-1 (higher confidence)
        self.assertEqual(len(merged), 2)

        # Confirm the duplicate was flagged as MERGED
        merged_dup = [b for b in merged if b.block_id == "ocr-1"][0]
        self.assertEqual(merged_dup.provenance, "MERGED")
        self.assertEqual(merged_dup.text, "OCR Higher Conf Text")

        # Confirm non-overlapping block was kept with OCR provenance
        non_overlap = [b for b in merged if b.block_id == "ocr-2"][0]
        self.assertEqual(non_overlap.provenance, "OCR")

    def test_layout_builder_coordinate_scaling(self):
        """Test OCR coordinate scaling from image pixels back to PDF points."""
        builder = OCRLayoutBuilder()

        # Image size 1000x1000px, PDF size 500x500pts (scale factor = 0.5)
        words = [
            {
                "text": "Testing",
                "bbox": (100, 200, 300, 400),
                "confidence": 0.90,
                "block_num": 1,
                "line_num": 1,
            }
        ]

        blocks = builder.build_layout_blocks(
            words, page_number=1, img_size=(1000, 1000), pdf_size=(500.0, 500.0)
        )

        self.assertEqual(len(blocks), 1)
        b = blocks[0]
        # Scaled bounds: (100*0.5, 200*0.5, 300*0.5, 400*0.5) => (50, 100, 150, 200)
        self.assertEqual(b.bounding_box.x0, 50.0)
        self.assertEqual(b.bounding_box.y0, 100.0)
        self.assertEqual(b.bounding_box.x1, 150.0)
        self.assertEqual(b.bounding_box.y1, 200.0)
        self.assertEqual(b.provenance, "OCR")

    def test_ocr_agent_caching_and_mock_run(self):
        """Verify that OCRAgent hashes pages, caches results, and hits cache on subsequent run."""
        mock_engine = MockOCREngine()
        # Initialize OCRAgent with custom mock engine injected
        agent = OCRAgent(char_threshold=50, engine=mock_engine)

        # Mock initial extraction result containing Page 1 (Rich) and Page 2 (Sparse)
        metadata = DocumentMetadataSchema(
            title="Test OCR Doc", author="Test", page_count=2, pdf_version="1.4"
        )
        pages = [
            PageSchema(page_number=1, width=595, height=842),
            PageSchema(page_number=2, width=595, height=842),
        ]
        blocks = [
            BlockSchema(
                block_id="b1",
                page_number=1,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                text="This is a rich digital page with plenty of characters to skip OCR.",
                bounding_box=BoundingBox(x0=50, y0=100, x1=500, y1=120),
                font_size=12.0,
                bold=False,
                italic=False,
                confidence=1.0,
            ),
            BlockSchema(
                block_id="b2",
                page_number=2,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                text="Sparse",
                bounding_box=BoundingBox(x0=50, y0=100, x1=100, y1=120),
                font_size=12.0,
                bold=False,
                italic=False,
                confidence=1.0,
            ),
        ]

        result = DocumentExtractionResult(
            upload_id="test-ocr-uuid",
            status="processed",
            metadata=metadata,
            pages=pages,
            blocks=blocks,
            tables=[],
            images=[],
            extraction_timestamp="2026-08-04T00:00:00Z",
            processing_time=0.1,
        )

        # Run 1: OCR processed Page 2
        res1 = agent.process_document(result, self.pdf_path, strategy=OCRStrategy.AUTO)
        self.assertEqual(res1.ocr_status, "completed")
        self.assertEqual(res1.ocr_engine, "mock-tesseract")
        self.assertTrue(any(b.provenance == "OCR" for b in res1.blocks))

        # Capture list of blocks and modify mock words to see if cache intercepts
        old_blocks_count = len(res1.blocks)
        mock_engine.mock_words = [{"text": "Changed text after cache", "bbox": (0,0,10,10), "confidence": 0.99, "block_num": 1, "line_num": 1}]

        # Run 2: Cache Hit on Page 2!
        res2 = agent.process_document(result, self.pdf_path, strategy=OCRStrategy.AUTO)
        self.assertEqual(len(res2.blocks), old_blocks_count)
        # Ensure we loaded cached text ("Chapter 1 Introduction") instead of changed mock text
        self.assertTrue(any("Chapter 1 Introduction" in b.text for b in res2.blocks))


if __name__ == "__main__":
    unittest.main()
