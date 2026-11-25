import os
import hashlib
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    hasher.update(page.read_contents())
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
    """Merge native PDF text extraction with OCR results, removing overlapping duplicates."""
    merged_blocks: List[BlockSchema] = []
    ocr_processed = set()

    for nb in native_blocks:
        overlapping_ocr = None
        for ob in ocr_blocks:
            if ob.block_id in ocr_processed:
                continue
            if _bbox_overlap(nb.bounding_box, ob.bounding_box) > 0.40:
                overlapping_ocr = ob
                break

        if overlapping_ocr:
            ocr_processed.add(overlapping_ocr.block_id)
            if nb.confidence >= overlapping_ocr.confidence:
                nb.provenance = "MERGED"
                merged_blocks.append(nb)
            else:
                overlapping_ocr.provenance = "MERGED"
                merged_blocks.append(overlapping_ocr)
        else:
            merged_blocks.append(nb)

    for ob in ocr_blocks:
        if ob.block_id not in ocr_processed:
            merged_blocks.append(ob)

    return merged_blocks


class OCRAgent:
    """Orchestrates page rendering, parallel image OCR, caching, and block merging."""

    def __init__(self, char_threshold: int = 50, engine=None):
        self.engine = engine or TesseractEngine()
        self.detector = PageDetector(char_threshold=char_threshold)
        self.layout_builder = OCRLayoutBuilder()

    def _run_single_page_ocr(self, task: Dict[str, Any]) -> Tuple[int, bool, List[BlockSchema], float]:
        """Worker method executing preprocessing, Tesseract OCR, and layout building for one page."""
        page_number = task["page_number"]
        page_hash = task["page_hash"]
        cache_file = task["cache_file"]
        pdf_size = task["pdf_size"]
        native_page_blocks = task["native_blocks"]
        raw_img_path = task["raw_img_path"]
        prep_img_path = task["prep_img_path"]

        success = False
        ocr_blocks: List[BlockSchema] = []

        try:
            for attempt in range(1, 3):
                try:
                    logger.info("Page {}: Running OCR processing (Attempt {}/2)", page_number, attempt)
                    prep_mode = "standard" if attempt == 1 else "aggressive"
                    preprocess_image_for_ocr(
                        raw_img_path, prep_img_path, tesseract_available=True, mode=prep_mode
                    )

                    words = self.engine.perform_ocr(prep_img_path)

                    avg_w_conf = (sum(w["confidence"] for w in words) / len(words)) if words else 0.0
                    if attempt == 1 and (len(words) < 5 or avg_w_conf < 0.42):
                        logger.warning(
                            "Page {}: Standard OCR yielded sparse/low-confidence output ({} words, avg conf {:.2f}). Retrying aggressive mode.",
                            page_number,
                            len(words),
                            avg_w_conf,
                        )
                        preprocess_image_for_ocr(
                            raw_img_path, prep_img_path, tesseract_available=True, mode="aggressive"
                        )
                        alt_words = self.engine.perform_ocr(prep_img_path)
                        alt_conf = (sum(w["confidence"] for w in alt_words) / len(alt_words)) if alt_words else 0.0
                        if len(alt_words) > len(words) or (len(alt_words) >= 5 and alt_conf > avg_w_conf):
                            words = alt_words

                    img_size = Image_size_helper(prep_img_path)
                    # Thread-local OCRLayoutBuilder instance because DocumentClassifier holds per-call stats
                    local_builder = OCRLayoutBuilder()
                    ocr_blocks = local_builder.build_layout_blocks(
                        words, page_number, img_size, pdf_size
                    )

                    cache_payload = {
                        "page_hash": page_hash,
                        "blocks": [b.model_dump() for b in ocr_blocks],
                        "confidence_stats": OCRConfidenceCalculator.build_confidence_metadata(words, page_number),
                    }
                    tmp_cache = f"{cache_file}.{uuid.uuid4().hex}.tmp"
                    with open(tmp_cache, "w", encoding="utf-8") as f:
                        json.dump(cache_payload, f, indent=2)
                    os.replace(tmp_cache, cache_file)

                    success = True
                    break
                except Exception as ocr_err:
                    logger.warning("Page {}: OCR attempt {} failed: {}", page_number, attempt, str(ocr_err))
                    time.sleep(0.1 * attempt)
        finally:
            for p in (raw_img_path, prep_img_path):
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

        if success:
            merged = merge_native_and_ocr_blocks(native_page_blocks, ocr_blocks)
            p_conf = OCRConfidenceCalculator.calculate_page_confidence(merged)
            return page_number, True, merged, p_conf

        logger.error("Page {}: OCR failed after retries. Falling back to native blocks.", page_number)
        return page_number, False, native_page_blocks, 1.0

    def process_document(
        self,
        extraction_result: DocumentExtractionResult,
        file_path: str,
        strategy: OCRStrategy = OCRStrategy.AUTO,
        progress_callback=None,
    ) -> DocumentExtractionResult:
        """Run OCR on pages matching the strategy in parallel, cache results, and merge layout blocks."""
        logger.info(
            "OCRAgent launching on document. Strategy: {}, Upload ID: {}",
            strategy.value,
            extraction_result.upload_id,
        )

        start_time = time.time()
        doc = fitz.open(file_path)
        total_pages = len(doc)

        ocr_pages_count = 0
        skipped_pages_count = 0
        failed_pages_count = 0
        page_confidences: List[float] = []
        updated_blocks: List[BlockSchema] = []
        ocr_tasks: List[Dict[str, Any]] = []

        # Group native blocks by page in O(N) instead of scanning per page
        blocks_by_page: Dict[int, List[BlockSchema]] = {}
        for b in extraction_result.blocks:
            blocks_by_page.setdefault(b.page_number, []).append(b)

        tesseract_available = self.engine.is_available()
        if not tesseract_available:
            logger.warning("Tesseract engine is not available on the host system.")

        completed_counter = 0
        progress_lock = threading.Lock()

        def _notify_progress(mode: str):
            nonlocal completed_counter
            if not progress_callback:
                return
            with progress_lock:
                completed_counter += 1
                progress_callback(completed_counter, total_pages, mode)

        try:
            for page_num_0indexed in range(total_pages):
                page_number = page_num_0indexed + 1
                page = doc[page_num_0indexed]
                native_page_blocks = blocks_by_page.get(page_number, [])

                if not self.detector.evaluate_page(page_number, native_page_blocks, strategy, page=page):
                    updated_blocks.extend(native_page_blocks)
                    page_confidences.append(1.0)
                    skipped_pages_count += 1
                    _notify_progress("digital")
                    continue

                page_hash = _compute_page_hash(page)
                cache_file = os.path.join(OCR_CACHE_DIR, f"{page_hash}.json")

                if os.path.exists(cache_file):
                    logger.info("Page {}: OCR Cache Hit!", page_number)
                    try:
                        with open(cache_file, "r", encoding="utf-8") as f:
                            cached_data = json.load(f)
                        cached_blocks = [
                            BlockSchema(
                                block_id=str(uuid.uuid4()),
                                page_number=page_number,
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
                            for cb_dict in cached_data["blocks"]
                        ]
                        merged = merge_native_and_ocr_blocks(native_page_blocks, cached_blocks)
                        updated_blocks.extend(merged)
                        page_confidences.append(OCRConfidenceCalculator.calculate_page_confidence(merged))
                        ocr_pages_count += 1
                        _notify_progress("ocr")
                        continue
                    except Exception as cache_err:
                        logger.warning("Failed to load OCR cache for page {}: {}", page_number, str(cache_err))

                if not tesseract_available:
                    logger.error("Page {}: OCR requested but Tesseract engine is unavailable.", page_number)
                    updated_blocks.extend(native_page_blocks)
                    page_confidences.append(1.0)
                    failed_pages_count += 1
                    _notify_progress("ocr")
                    continue

                # Render 300 DPI image in main thread (PyMuPDF is not thread-safe)
                unique_tag = f"{page_hash}_{page_number}_{uuid.uuid4().hex[:6]}"
                raw_img_path = os.path.join(TEMP_OCR_DIR, f"{unique_tag}_raw.png")
                prep_img_path = os.path.join(TEMP_OCR_DIR, f"{unique_tag}_prep.png")
                pix = page.get_pixmap(dpi=300)
                pix.save(raw_img_path)

                ocr_tasks.append(
                    {
                        "page_number": page_number,
                        "page_hash": page_hash,
                        "cache_file": cache_file,
                        "pdf_size": (page.rect.width, page.rect.height),
                        "native_blocks": native_page_blocks,
                        "raw_img_path": raw_img_path,
                        "prep_img_path": prep_img_path,
                    }
                )
        finally:
            doc.close()

        # Execute uncached OCR pages in parallel across worker threads
        if ocr_tasks:
            max_workers = min(4, max(2, os.cpu_count() or 2), len(ocr_tasks))
            logger.info("Running parallel OCR for {} pages using {} workers", len(ocr_tasks), max_workers)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(self._run_single_page_ocr, t) for t in ocr_tasks]
                for fut in as_completed(futures):
                    _pnum, ok, merged_blocks, p_conf = fut.result()
                    updated_blocks.extend(merged_blocks)
                    page_confidences.append(p_conf)
                    if ok:
                        ocr_pages_count += 1
                    else:
                        failed_pages_count += 1
                    _notify_progress("ocr")

        updated_blocks.sort(key=lambda b: (b.page_number, b.reading_order))
        for idx, b in enumerate(updated_blocks):
            b.reading_order = idx + 1

        ocr_duration = round(time.time() - start_time, 2)
        doc_confidence = OCRConfidenceCalculator.calculate_document_confidence(page_confidences)

        if ocr_pages_count == 0 and failed_pages_count == 0:
            final_status = "skipped"
        elif failed_pages_count > 0:
            final_status = "failed"
        else:
            final_status = "completed"

        extraction_result.blocks = updated_blocks
        extraction_result.ocr_status = final_status
        extraction_result.ocr_engine = self.engine.get_name()
        extraction_result.ocr_version = self.engine.get_version()
        extraction_result.ocr_confidence = doc_confidence
        extraction_result.ocr_language = "en"
        extraction_result.ocr_processing_time = ocr_duration

        logger.info(
            "OCRAgent completed in {}s. Pages OCRed: {}, Failed: {}, Skipped: {}, Confidence: {}",
            ocr_duration,
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
