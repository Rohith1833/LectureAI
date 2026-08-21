import os
import sys
import unittest
from datetime import datetime, timezone

# Add app directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.document import Base
from app.schemas.document import BlockType
from app.services import pdf_extractor
from app.services.document_classifier import DocumentClassifier, ClassifierConfig
from app.repositories.document_repository import DocumentRepository


class TestDocumentAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 1. Create a mock PDF for testing
        cls.pdf_path = os.path.abspath("test_document.pdf")
        import fitz

        doc = fitz.open()
        page = doc.new_page(width=595, height=842)

        # Draw text to simulate columns/headings
        page.insert_text(
            (50, 100),
            "LectureAI Foundations Chapter",
            fontsize=26,
            fontname="helv",
        )
        page.insert_text(
            (50, 160),
            "1. Introduction to Advanced Agents",
            fontsize=18,
            fontname="helv",
        )
        page.insert_text(
            (50, 200),
            "This is a standard body paragraph on the left column.",
            fontsize=10,
            fontname="helv",
        )

        # Draw a list
        page.insert_text((50, 240), "- First list objective", fontsize=10)
        page.insert_text((50, 260), "- Second list objective", fontsize=10)

        # Draw text on right side to simulate two columns
        page.insert_text(
            (320, 200),
            "This is a body paragraph on the right column.",
            fontsize=10,
            fontname="helv",
        )

        doc.save(cls.pdf_path)
        doc.close()

        # 2. Setup SQLite database in memory
        cls.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.pdf_path):
            os.remove(cls.pdf_path)

    def setUp(self):
        self.db = self.SessionLocal()

    def tearDown(self):
        self.db.close()

    def test_pdf_extractor_returns_canonical_model(self):
        """Verify that pdf_extractor parses layouts and returns Canonical Pydantic schemas."""
        upload_id = "test-upload-uuid"
        result = pdf_extractor.extract_pdf_document(upload_id, self.pdf_path)

        # Assert structure
        self.assertEqual(result.upload_id, upload_id)
        self.assertEqual(result.status, "processed")
        self.assertEqual(result.metadata.page_count, 1)
        self.assertTrue(result.processing_time >= 0.0)

        # Verify block detection
        self.assertTrue(len(result.blocks) >= 4)

        # Verify block types
        heading_blocks = [b for b in result.blocks if b.block_type == BlockType.HEADING]
        self.assertTrue(len(heading_blocks) >= 2)
        self.assertEqual(heading_blocks[0].heading_level, 1)  # size 26
        self.assertEqual(heading_blocks[1].heading_level, 2)  # size 18

        list_blocks = [b for b in result.blocks if b.block_type == BlockType.LIST]
        self.assertTrue(len(list_blocks) >= 1)

        # Verify reading order sorting (Left column before Right column)
        left_body = [
            b
            for b in result.blocks
            if b.block_type == BlockType.PARAGRAPH
            and "left column" in b.text
        ]
        right_body = [
            b
            for b in result.blocks
            if b.block_type == BlockType.PARAGRAPH
            and "right column" in b.text
        ]

        self.assertTrue(len(left_body) == 1)
        self.assertTrue(len(right_body) == 1)

        # Left column centroid mid_x is smaller, so sorted first in two-column layouts
        self.assertTrue(left_body[0].reading_order < right_body[0].reading_order)

        # Verify relationship pointers
        for i in range(1, len(result.blocks)):
            self.assertEqual(
                result.blocks[i].previous_block_id, result.blocks[i - 1].block_id
            )
            self.assertEqual(
                result.blocks[i - 1].next_block_id, result.blocks[i].block_id
            )

    def test_document_repository_saves_canonical_model(self):
        """Verify that DocumentRepository commits canonical model to SQLite correctly."""
        upload_id = "test-db-persist-uuid"
        result = pdf_extractor.extract_pdf_document(upload_id, self.pdf_path)

        # Persist using repo
        repo = DocumentRepository(self.db)
        db_doc = repo.save_extraction_result(result)

        # Query and assert db entries
        queried_doc = repo.get_document(db_doc.id)
        self.assertIsNotNone(queried_doc)
        self.assertEqual(queried_doc.upload_id, upload_id)
        self.assertEqual(queried_doc.status, "processed")

        # Verify pages count
        self.assertEqual(len(queried_doc.pages), 1)
        self.assertEqual(queried_doc.pages[0].page_number, 1)

        # Verify blocks count
        self.assertTrue(len(queried_doc.blocks) >= 4)
        self.assertEqual(queried_doc.blocks[0].document_id, db_doc.id)

        # Verify metadata
        self.assertIsNotNone(queried_doc.metadata_rel)
        self.assertEqual(queried_doc.metadata_rel.page_count, 1)

        # Verify classification reasoning is stored in extra_metadata
        block_db = queried_doc.blocks[0]
        self.assertIsNotNone(block_db.extra_metadata)
        self.assertIn("classification_reasoning", block_db.extra_metadata)
        reasoning = block_db.extra_metadata["classification_reasoning"]
        self.assertIn("net_score", reasoning)
        self.assertIn("dominant_size", reasoning)

    def test_relative_classification(self):
        """Verify that classification is relative to document-wide font statistics."""
        # Setup classifier
        classifier = DocumentClassifier()

        # Case A: Document with dominant body size = 15.0
        raw_doc_a = [
            [
                {"text": "A standard body paragraph.", "font_size": 15.0, "font_family": "Arial", "bold": False, "type": 0},
                {"text": "Another standard body paragraph.", "font_size": 15.0, "font_family": "Arial", "bold": False, "type": 0},
                {"text": "Some text of interest.", "font_size": 15.0, "font_family": "Arial", "bold": False, "type": 0},
            ]
        ]
        classifier.perform_first_pass(raw_doc_a)
        self.assertEqual(classifier.stats.dominant_size, 15.0)

        # Block with font_size 15 should NOT be classified as heading (since it is body)
        test_block = {"text": "Heading test block", "font_size": 15.0, "font_family": "Arial", "bold": False, "bbox": (50, 200, 200, 250)}
        b_type, confidence, _ = classifier.classify_block(test_block, None, None, 800.0)
        self.assertNotEqual(b_type, BlockType.HEADING)

        # Case B: Document with dominant body size = 10.0
        classifier_b = DocumentClassifier()
        raw_doc_b = [
            [
                {"text": "A standard body paragraph.", "font_size": 10.0, "font_family": "Arial", "bold": False, "type": 0},
                {"text": "Another standard body paragraph.", "font_size": 10.0, "font_family": "Arial", "bold": False, "type": 0},
                {"text": "Short note.", "font_size": 10.0, "font_family": "Arial", "bold": False, "type": 0},
            ]
        ]
        classifier_b.perform_first_pass(raw_doc_b)
        self.assertEqual(classifier_b.stats.dominant_size, 10.0)

        # In Document B, a block with font_size 15 is significantly larger than body (+5.0)
        # and should score highly enough to be classified as HEADING
        test_block_large = {"text": "Real chapter title text here", "font_size": 15.0, "font_family": "Arial", "bold": True, "bbox": (50, 200, 200, 220)}
        b_type_b, confidence_b, reasoning_b = classifier_b.classify_block(test_block_large, None, None, 800.0)
        self.assertEqual(b_type_b, BlockType.HEADING)

    def test_configurable_classifier_weights(self):
        """Verify that classifier config weights can be customized without editing code."""
        # Normal configuration: bold weight is 1.0, length weight is 0.8
        config_normal = ClassifierConfig(weight_bold=1.0)
        classifier_normal = DocumentClassifier(config=config_normal)
        classifier_normal.stats.dominant_size = 10.0

        test_block = {
            "text": "A paragraph that is bold.",
            "font_size": 10.0,
            "font_family": "Arial",
            "bold": True,
            "bbox": (50, 100, 300, 150),
        }
        _, _, reasoning_normal = classifier_normal.classify_block(test_block, None, None, 800.0)

        # Customize weights
        config_custom = ClassifierConfig(weight_bold=5.0)
        classifier_custom = DocumentClassifier(config=config_custom)
        classifier_custom.stats.dominant_size = 10.0
        _, _, reasoning_custom = classifier_custom.classify_block(test_block, None, None, 800.0)

        self.assertGreater(reasoning_custom["bold_score"], reasoning_normal["bold_score"])

    def test_unknown_classification_fallback(self):
        """Verify low confidence blocks are classified as UNKNOWN instead of promoted to paragraph."""
        config = ClassifierConfig(
            weight_size=1.0,
            weight_punctuation=2.0,
            unknown_threshold=0.45,
        )
        classifier = DocumentClassifier(config=config)
        classifier.stats.dominant_size = 12.0

        # Margins check: borderline score that lands inside the uncertainty zone (0.35 <= confidence < 0.65)
        test_block = {
            "text": "An Ambiguous Bold Heading Text.",  # Ends with period, title case, short
            "font_size": 13.0,  # size_diff = 1.0 -> size_score = 0.0
            "font_family": "Arial",
            "bold": True,  # bold_score = +0.8
            "bbox": (50, 500, 300, 515),
        }
        b_type, confidence, reasoning = classifier.classify_block(test_block, None, None, 800.0)
        # Check that it falls in the uncertainty zone
        self.assertTrue(0.35 <= confidence < 0.65, f"Confidence {confidence} not in [0.35, 0.65)")
        self.assertEqual(b_type, BlockType.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
