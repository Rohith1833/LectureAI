import os
import hashlib
import json
import time
from typing import List, Dict, Any, Tuple
import fitz  # PyMuPDF
from loguru import logger

from app.schemas.document import DocumentExtractionResult, BlockSchema, BoundingBox, BlockType
from app.services.ocr.tesseract_engine import TesseractEngine
from app.services.ocr.preprocessing import preprocess_image_for_ocr
from app.services.ocr.page_detector import PageDetector, OCRStrategy
from app.services.ocr.layout_builder import OCRLayoutBuilder
from app.services.ocr.confidence import OCRConfidenceCalculator
from app.core.storage import STORAGE_ROOT

# Setup cache paths
OCR_CACHE_DIR = os.path.join(STORAGE_ROOT, "cache", "ocr")
TEMP_OCR_DIR = os.path.join(STORAGE_ROOT, "temp", "ocr")

os.makedirs(OCR_CACHE_DIR, exist_ok=True)
os.makedirs(TEMP_OCR_DIR, exist_ok=True)


def _compute_page_hash(page: fitz.Page) -> str:
    """Generate a unique SHA-256 fingerprint for a PDF page based on its contents and dimensions."""
    hasher = hashlib.sha256()
    # Read raw content stream
    hasher.update(page.read_contents())
    # Add page dimensions to fingerprint
    hasher.update(str(page.rect).encode())
    return hasher.hexdigest()


def _bbox_overlap(box1: BoundingBox, box2: BoundingBox) -> float:
    """Calculate the overlap ratio between two bounding boxes (Intersection over smaller Area)."""
    x0 = max(box1.x0, box2.x0)
    y0 = max(box1.y0, box2.y0)
    x1 = min(box1.x1, box2.x1)
    y1 = min(box1.y1, box2.y1)

    if x1 <= x0 or y1 <= y0:
        return 0.0

    intersection = (x1 - x0) * (y1 - y0)
    area1 = (box1.x1 - box1.x0) * (box1.y1 - box1.y0)
    area2 = (box2.x1 - box2.x0) * (box2.y1 - box2.y0)

    smaller_area = min(area1, area2)
    if smaller_area <= 0:
        return 0.0

    return intersection / smaller_area


def merge_native_and_ocr_blocks(
    native_blocks: List[BlockSchema], ocr_blocks: List[BlockSchema]
) -> List[BlockSchema]:
    """Merge native PDF text extraction with OCR results, removing overlapping duplicates.

    Preserves the element with the highest confidence, tagging resolved duplicates as 'MERGED'.
    """
    merged_blocks: List[BlockSchema] = []
    ocr_processed = set()

    for nb in native_blocks:
        overlapping_ocr = None
        for ob in ocr_blocks:
            if ob.block_id in ocr_processed:
                continue
            # Check overlap threshold (40%)
            if _bbox_overlap(nb.bounding_box, ob.bounding_box) > 0.40:
                overlapping_ocr = ob
                break

        if overlapping_ocr:
            ocr_processed.add(overlapping_ocr.block_id)
            # Compare confidence: native vs OCR
            if nb.confidence >= overlapping_ocr.confidence:
                # Keep native block but label it MERGED to show it was validated
                nb.provenance = "MERGED"
                merged_blocks.append(nb)
                logger.debug("Merging: keeping native block over OCR (higher confidence)")
            else:
                overlapping_ocr.provenance = "MERGED"
                merged_blocks.append(overlapping_ocr)
                logger.debug("Merging: keeping OCR block over native (higher confidence)")
        else:
            merged_blocks.append(nb)

    # Add remaining OCR blocks that had no native overlaps
    for ob in ocr_blocks:
        if ob.block_id not in ocr_processed:
            merged_blocks.append(ob)

    return merged_blocks


class OCRAgent:
    """Orchestrates page rendering, image enhancements, cache inspection, OCR execution, and block merging."""

    def __init__(self, char_threshold: int = 50, engine=None):
        self.engine = engine or TesseractEngine()
        self.detector = PageDetector(char_threshold=char_threshold)
        self.layout_builder = OCRLayoutBuilder()

    def process_document(
        self,
        extraction_result: DocumentExtractionResult,
        file_path: str,
        strategy: OCRStrategy = OCRStrategy.AUTO,
    ) -> DocumentExtractionResult:
        """Run OCR on pages matching the strategy, cache results, merge layout blocks, and compile auditing metrics."""
        logger.info(
            "OCRAgent launching on document. Strategy: {}, Upload ID: {}",
            strategy.value,
            extraction_result.upload_id,
        )

        start_time = time.time()
        doc = fitz.open(file_path)
        try:
            ocr_pages_count = 0
            skipped_pages_count = 0
            failed_pages_count = 0

            page_confidences = []
            updated_blocks: List[BlockSchema] = []

            # Keep tracks of all blocks not processed by OCR to carry them over
            non_ocr_blocks = [b for b in extraction_result.blocks]

            tesseract_available = self.engine.is_available()
            if not tesseract_available:
                logger.warning("Tesseract engine is not available on the host system.")

            for page_num_0indexed in range(len(doc)):
                page_number = page_num_0indexed + 1
                page = doc[page_num_0indexed]

                # 1. Screen page using Detector
                native_page_blocks = [b for b in extraction_result.blocks if b.page_number == page_number]
                
                # Remove native blocks from our accumulator for this page (we will either restore, replace, or merge them)
                non_ocr_blocks = [b for b in non_ocr_blocks if b.page_number != page_number]

                if not self.detector.evaluate_page(page_number, native_page_blocks, strategy):
                    # Page skipped OCR: restore original native blocks and log page confidence 1.0
                    updated_blocks.extend(native_page_blocks)
                    page_confidences.append(1.0)
                    skipped_pages_count += 1
                    continue

                # 2. Check OCR Cache
                page_hash = _compute_page_hash(page)
                cache_file = os.path.join(OCR_CACHE_DIR, f"{page_hash}.json")

                if os.path.exists(cache_file):
                    logger.info("Page {}: OCR Cache Hit!", page_number)
                    try:
                        with open(cache_file, "r") as f:
                            cached_data = json.load(f)
                        
                        cached_blocks = []
                        for cb_dict in cached_data["blocks"]:
                            # Reconstruct BlockSchema objects
                            cached_blocks.append(
                                BlockSchema(
                                    block_id=cb_dict["block_id"],
                                    page_number=page_number,  # preserve current page number mapping
                                    reading_order=cb_dict["reading_order"],
                                    block_type=BlockType(cb_dict["block_type"]),
                                    text=cb_dict["text"],
                                    bounding_box=BoundingBox(**cb_dict["bounding_box"]),
                                    font_size=cb_dict.get("font_size"),
                                    font_family=cb_dict.get("font_family"),
                                    bold=cb_dict.get("bold", False),
                                    italic=cb_dict.get("italic", False),
                                    confidence=cb_dict.get("confidence", 1.0),
                                    provenance=cb_dict.get("provenance", "OCR"),
                                    extra_metadata=cb_dict.get("extra_metadata"),
                                )
                            )

                        merged = merge_native_and_ocr_blocks(native_page_blocks, cached_blocks)
                        updated_blocks.extend(merged)

                        p_conf = OCRConfidenceCalculator.calculate_page_confidence(merged)
                        page_confidences.append(p_conf)
                        ocr_pages_count += 1
                        continue
                    except Exception as cache_err:
                        logger.warning("Failed to load OCR cache for page {}: {}", page_number, str(cache_err))

                # 3. Perform OCR with Retry Logic
                if not tesseract_available:
                    # Graceful fallback: set failed page counts and log error status
                    logger.error("Page {}: OCR requested but Tesseract engine is unavailable.", page_number)
                    updated_blocks.extend(native_page_blocks)  # fall back to native text
                    page_confidences.append(1.0)
                    failed_pages_count += 1
                    continue

                # Page requires active OCR run
                temp_image_path = os.path.join(TEMP_OCR_DIR, f"{page_hash}_raw.png")
                temp_prep_path = os.path.join(TEMP_OCR_DIR, f"{page_hash}_prep.png")

                success = False
                ocr_blocks = []
                
                for attempt in range(1, 4):
                    try:
                        logger.info("Page {}: Running OCR processing (Attempt {}/3)", page_number, attempt)
                        
                        # Render page at 300 DPI (High Resolution Normalization)
                        pix = page.get_pixmap(dpi=300)
                        pix.save(temp_image_path)

                        # Run Image Preprocessing
                        preprocess_image_for_ocr(temp_image_path, temp_prep_path, tesseract_available=True)

                        # Execute Tesseract Engine
                        words = self.engine.perform_ocr(temp_prep_path)

                        # Layout Construction
                        img_size = Image_size_helper(temp_prep_path)
                        pdf_size = (page.rect.width, page.rect.height)
                        ocr_blocks = self.layout_builder.build_layout_blocks(
                            words, page_number, img_size, pdf_size
                        )

                        # Cache Results
                        cache_payload = {
                            "page_hash": page_hash,
                            "blocks": [b.model_dump() for b in ocr_blocks],
                            "confidence_stats": OCRConfidenceCalculator.build_confidence_metadata(words, page_number),
                        }
                        with open(cache_file, "w") as f:
                            json.dump(cache_payload, f, indent=2)

                        success = True
                        break
                    except Exception as ocr_err:
                        logger.warning("Page {}: OCR run failed on attempt {}: {}", page_number, attempt, str(ocr_err))
                        time.sleep(0.1 * attempt) # linear backoff

                # Clean up temp image files
                for p in [temp_image_path, temp_prep_path]:
                    if os.path.exists(p):
                        try:
                            os.remove(p)
                        except Exception:
                            pass

                if success:
                    # Merge OCR blocks with native blocks
                    merged = merge_native_and_ocr_blocks(native_page_blocks, ocr_blocks)
                    updated_blocks.extend(merged)
                    p_conf = OCRConfidenceCalculator.calculate_page_confidence(merged)
                    page_confidences.append(p_conf)
                    ocr_pages_count += 1
                else:
                    logger.error("Page {}: OCR failed after all 3 retries. Skipping page OCR.", page_number)
                    updated_blocks.extend(native_page_blocks)
                    page_confidences.append(1.0)
                    failed_pages_count += 1
        finally:
            doc.close()

        # Combine processed blocks with untouched blocks
        all_final_blocks = non_ocr_blocks + updated_blocks
        
        # Recalculate global reading_order sequences on merged blocks
        all_final_blocks.sort(key=lambda b: (b.page_number, b.reading_order))
        for idx, b in enumerate(all_final_blocks):
            b.reading_order = idx + 1

        # Compile overall document auditing parameters
        ocr_duration = round(time.time() - start_time, 2)
        doc_confidence = OCRConfidenceCalculator.calculate_document_confidence(page_confidences)

        # Decide overall status string
        if ocr_pages_count == 0:
            final_status = "skipped"
        elif failed_pages_count > 0:
            final_status = "failed"
        else:
            final_status = "completed"

        # Update extraction results schema fields
        extraction_result.blocks = all_final_blocks
        extraction_result.ocr_status = final_status
        extraction_result.ocr_engine = self.engine.get_name()
        extraction_result.ocr_version = self.engine.get_version()
        extraction_result.ocr_confidence = doc_confidence
        extraction_result.ocr_language = "en"  # default language
        extraction_result.ocr_processing_time = ocr_duration

        logger.info(
            "OCRAgent run completed. Pages OCRed: {}, Failed: {}, Skipped: {}, Document Confidence: {}",
            ocr_pages_count,
            failed_pages_count,
            skipped_pages_count,
            doc_confidence,
        )

        return extraction_result


def Image_size_helper(path: str) -> Tuple[int, int]:
    from PIL import Image
    try:
        with Image.open(path) as img:
            return img.size
    except Exception:
        return (1000, 1000)
