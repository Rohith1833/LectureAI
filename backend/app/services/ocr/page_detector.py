from typing import List, Optional
from enum import Enum
import fitz
from loguru import logger

from app.schemas.document import BlockSchema


class OCRStrategy(str, Enum):
    AUTO = "AUTO"
    FORCE = "FORCE"
    SKIP = "SKIP"


class PageDetector:
    """Intelligent page inspector that determines if a page requires OCR based on text and image coverage."""

    def __init__(self, char_threshold: int = 50):
        self.char_threshold = char_threshold

    def evaluate_page(
        self,
        page_number: int,
        blocks: List[BlockSchema],
        strategy: OCRStrategy = OCRStrategy.AUTO,
        page: Optional[fitz.Page] = None,
    ) -> bool:
        """Assess if a page should go through OCR processing."""
        if strategy == OCRStrategy.SKIP:
            logger.info("Page {}: SKIP strategy active, skipping OCR", page_number)
            return False

        if strategy == OCRStrategy.FORCE:
            logger.info("Page {}: FORCE strategy active, triggering OCR", page_number)
            return True

        page_blocks = [b for b in blocks if b.page_number == page_number]
        alnum_chars = sum(sum(1 for c in (b.text or "") if c.isalnum()) for b in page_blocks)

        if alnum_chars < self.char_threshold:
            logger.info(
                "Page {}: AUTO strategy -> low digital text ({} alnum chars < {}). Needs OCR: True",
                page_number,
                alnum_chars,
                self.char_threshold,
            )
            return True

        # Check if page is dominated by a large scanned image (e.g. scanned page with a digital header/footer)
        if page is not None and alnum_chars < 220:
            page_area = max(1.0, page.rect.width * page.rect.height)
            max_img_ratio = 0.0
            try:
                for img_info in page.get_images(full=True):
                    for r in page.get_image_rects(img_info[0]):
                        ratio = (r.width * r.height) / page_area
                        if ratio > max_img_ratio:
                            max_img_ratio = ratio
            except Exception:
                pass

            if max_img_ratio >= 0.35:
                logger.info(
                    "Page {}: AUTO strategy -> large image ({:.0%} of page) with sparse digital text ({} chars). Needs OCR: True",
                    page_number,
                    max_img_ratio,
                    alnum_chars,
                )
                return True

        logger.info(
            "Page {}: AUTO strategy -> digital text sufficient ({} alnum chars). Needs OCR: False",
            page_number,
            alnum_chars,
        )
        return False
