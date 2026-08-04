from typing import List
from enum import Enum
from loguru import logger

from app.schemas.document import BlockSchema


class OCRStrategy(str, Enum):
    AUTO = "AUTO"
    FORCE = "FORCE"
    SKIP = "SKIP"


class PageDetector:
    """Intelligent page inspector that determines if a page requires OCR based on strategy."""

    def __init__(self, char_threshold: int = 50):
        self.char_threshold = char_threshold

    def evaluate_page(
        self, page_number: int, blocks: List[BlockSchema], strategy: OCRStrategy = OCRStrategy.AUTO
    ) -> bool:
        """Assess if a page should go through OCR processing."""
        if strategy == OCRStrategy.SKIP:
            logger.info("Page {}: SKIP strategy active, skipping OCR", page_number)
            return False

        if strategy == OCRStrategy.FORCE:
            logger.info("Page {}: FORCE strategy active, triggering OCR", page_number)
            return True

        # AUTO mode: scan character volume
        page_blocks = [b for b in blocks if b.page_number == page_number]
        total_chars = sum(len(b.text) for b in page_blocks if b.text)

        needs_ocr = total_chars < self.char_threshold
        logger.info(
            "Page {}: AUTO strategy active. Digital characters found: {}. Needs OCR: {}",
            page_number,
            total_chars,
            needs_ocr,
        )
        return needs_ocr
