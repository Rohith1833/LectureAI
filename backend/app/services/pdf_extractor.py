import os
import time
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional
import fitz  # PyMuPDF
from fastapi import HTTPException, status
from loguru import logger

from app.schemas.document import (
    DocumentExtractionResult,
    DocumentMetadataSchema,
    PageSchema,
    BlockSchema,
    TableSchema,
    ImageSchema,
    BlockType,
    BoundingBox,
)
from app.services.reading_order import sort_and_link_blocks
from app.services.document_classifier import DocumentClassifier


def _is_inside_table(bbox: Tuple[float, float, float, float], tables: List[TableSchema]) -> bool:
    """Helper to check if a block's bounding box is entirely within any table bounding box."""
    bx0, by0, bx1, by1 = bbox
    for t in tables:
        tx = t.bounding_box
        # Check if the block bbox coordinates fall inside the table coordinates with padding
        if bx0 >= tx.x0 - 5 and by0 >= tx.y0 - 5 and bx1 <= tx.x1 + 5 and by1 <= tx.y1 + 5:
            return True
    return False


def extract_pdf_document(upload_id: str, file_path: str) -> DocumentExtractionResult:
    """Read a local PDF Textbook using PyMuPDF and output the Canonical Document Model."""
    start_time = time.time()
    logger.info("Starting PDF extraction service for upload: {}", upload_id)

    if not os.path.exists(file_path):
        logger.error("PDF Extraction failed: File not found at path '{}'", file_path)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The uploaded textbook file could not be found in storage.",
        )

    # 1. Open PDF document with error handling
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        logger.error("Failed to open PDF file via PyMuPDF: {}", str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to parse the PDF file. It might be corrupted or in an unsupported format.",
        )

    try:
        # 2. Check encryption / Password protection
        if doc.is_encrypted:
            logger.warning("PDF extraction aborted: File is password protected.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The uploaded PDF file is password protected or encrypted.",
            )

        page_count = len(doc)
        if page_count == 0:
            logger.warning("PDF extraction aborted: File contains zero pages.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The uploaded PDF file contains no pages.",
            )

        # 3. Extract Document Metadata
        meta = doc.metadata or {}
        pdf_version = meta.get("format") or "1.4"
        doc_metadata = DocumentMetadataSchema(
            title=meta.get("title") or os.path.basename(file_path),
            author=meta.get("author") or "Unknown Author",
            subject=meta.get("subject"),
            keywords=meta.get("keywords"),
            creation_date=meta.get("creationDate"),
            producer=meta.get("producer"),
            page_count=page_count,
            pdf_version=pdf_version,
            language=None,  # to be auto-detected if needed
        )

        # 4. First Pass: Loop through pages to collect raw blocks and metadata
        raw_pages_data = []
        canonical_pages: List[PageSchema] = []
        canonical_tables: List[TableSchema] = []
        canonical_images: List[ImageSchema] = []

        total_characters = 0

        for page_num_0indexed in range(page_count):
            page_number = page_num_0indexed + 1
            page = doc[page_num_0indexed]
            rect = page.rect
            width = rect.width
            height = rect.height

            # Register Page
            canonical_pages.append(
                PageSchema(page_number=page_number, width=width, height=height)
            )

            # A. Extract Tables (PyMuPDF find_tables())
            page_tables: List[TableSchema] = []
            try:
                table_finder = page.find_tables()
                for t_idx, table in enumerate(table_finder.tables):
                    tb_coords = table.bbox
                    t_bbox = BoundingBox(
                        x0=tb_coords[0], y0=tb_coords[1], x1=tb_coords[2], y1=tb_coords[3]
                    )
                    cell_data = table.extract()

                    # Filter out empty cells
                    if cell_data:
                        t_schema = TableSchema(
                            table_id=str(uuid.uuid4()),
                            page_number=page_number,
                            bounding_box=t_bbox,
                            rows_count=len(cell_data),
                            columns_count=len(cell_data[0]) if cell_data else 0,
                            data=cell_data,
                        )
                        page_tables.append(t_schema)
                        canonical_tables.append(t_schema)
            except Exception as tbl_err:
                logger.warning(
                    "Table extraction failed on page {}: {}", page_number, str(tbl_err)
                )

            # B. Register Images
            page_image_rects: List[Tuple[float, float, float, float]] = []
            page_images: List[ImageSchema] = []
            try:
                image_info_list = page.get_images(full=True)
                for img_info in image_info_list:
                    xref = img_info[0]
                    # Get position of image on the page
                    rects = page.get_image_rects(xref)
                    for r in rects:
                        img_bbox = BoundingBox(x0=r.x0, y0=r.y0, x1=r.x1, y1=r.y1)
                        # Avoid duplicates
                        if (r.x0, r.y0, r.x1, r.y1) in page_image_rects:
                            continue
                        page_image_rects.append((r.x0, r.y0, r.x1, r.y1))

                        img_schema = ImageSchema(
                            image_id=str(uuid.uuid4()),
                            page_number=page_number,
                            bounding_box=img_bbox,
                            width=r.width,
                            height=r.height,
                            caption=None,
                        )
                        page_images.append(img_schema)
                        canonical_images.append(img_schema)
            except Exception as img_err:
                logger.warning(
                    "Image extraction failed on page {}: {}", page_number, str(img_err)
                )

            # C. Extract Text Blocks using "dict" to preserve styles
            text_dict = page.get_text("dict")
            raw_page_blocks: List[Dict[str, Any]] = []

            for block in text_dict.get("blocks", []):
                # block type 0 is text, 1 is image
                if block.get("type") != 0:
                    continue

                bbox_coords = block.get("bbox", (0, 0, 0, 0))

                # Check if block text lies inside tables -> if so, skip to avoid duplicate table cell content
                if _is_inside_table(bbox_coords, page_tables):
                    continue

                # Parse lines and spans to reconstruct text and styles
                block_text_parts = []
                sizes = []
                fonts = []
                is_bold = False
                is_italic = False

                for line in block.get("lines", []):
                    line_text = ""
                    for span in line.get("spans", []):
                        span_text = span.get("text", "")
                        line_text += span_text
                        sizes.append(span.get("size", 10.0))
                        fonts.append(span.get("font", "Arial"))

                        # Span flags check: 16 = bold, 2 = italic
                        flags = span.get("flags", 0)
                        if flags & 16 or "bold" in span.get("font", "").lower():
                            is_bold = True
                        if flags & 2 or "italic" in span.get("font", "").lower():
                            is_italic = True

                    block_text_parts.append(line_text)

                block_text = "\n".join(block_text_parts)
                if not block_text.strip():
                    continue

                # Accumulate characters to check if PDF needs OCR later
                total_characters += len(block_text)

                avg_size = sum(sizes) / len(sizes) if sizes else 10.0
                primary_font = max(set(fonts), key=fonts.count) if fonts else "Arial"

                raw_page_blocks.append(
                    {
                        "block_id": str(uuid.uuid4()),
                        "bbox": bbox_coords,
                        "text": block_text,
                        "font_size": avg_size,
                        "font_family": primary_font,
                        "bold": is_bold,
                        "italic": is_italic,
                        "type": 0,
                    }
                )

            raw_pages_data.append(
                {
                    "page_number": page_number,
                    "width": width,
                    "height": height,
                    "raw_blocks": raw_page_blocks,
                    "images": page_images,
                }
            )

        # 5. Initialize Document Classifier and run Pass 1 (Dominant font stats)
        classifier = DocumentClassifier()
        classifier.perform_first_pass([p["raw_blocks"] for p in raw_pages_data])

        # 6. Run Pass 2 (Multi-feature layout scoring and context classification)
        all_blocks_flat = []
        for page_data in raw_pages_data:
            page_height = page_data["height"]
            raw_blocks = page_data["raw_blocks"]
            num_blocks = len(raw_blocks)

            for idx, block in enumerate(raw_blocks):
                prev_block = raw_blocks[idx - 1] if idx > 0 else None
                next_block = raw_blocks[idx + 1] if idx < num_blocks - 1 else None

                # Perform classification
                b_type, confidence, reasoning = classifier.classify_block(
                    block, prev_block, next_block, page_height
                )

                block["block_type"] = b_type
                block["confidence"] = confidence
                block["extra_metadata"] = {"classification_reasoning": reasoning}
                block["heading_level"] = None  # to be assigned dynamically next

                all_blocks_flat.append(block)

        # 7. Dynamically assign heading levels based on sizes distribution
        classifier.assign_heading_levels(all_blocks_flat)

        # 8. Post-process blocks: sort layout columns and link sequences
        canonical_blocks: List[BlockSchema] = []
        for page_data in raw_pages_data:
            page_number = page_data["page_number"]
            width = page_data["width"]
            height = page_data["height"]
            raw_blocks = page_data["raw_blocks"]
            page_images = page_data["images"]

            # D. Associate Captions to Images (Heuristic: match caption block located close to image bbox)
            for img in page_images:
                iy1 = img.bounding_box.y1
                # Search for caption block close below image (within 30 points)
                for rpb in raw_blocks:
                    if rpb["block_type"] == BlockType.CAPTION:
                        ry0 = rpb["bbox"][1]
                        if 0 <= (ry0 - iy1) <= 30.0:
                            img.caption = rpb["text"]
                            break

            # E. Sort page blocks layout and link previous/next IDs
            sorted_page_blocks = sort_and_link_blocks(
                raw_blocks, page_number, width, height
            )
            canonical_blocks.extend(sorted_page_blocks)

        # 9. Finalize OCR Fallback Checks
        status_str = "processed"
        if total_characters < 50 * page_count:
            logger.warning(
                "Document has very low text content ({} chars across {} pages). Flagging DocumentNeedsOCR.",
                total_characters,
                page_count,
            )
            status_str = "needs_ocr"

    except Exception as ex:
        logger.error("Process aborted due to extraction exception: {}", str(ex))
        if not isinstance(ex, HTTPException):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An error occurred while extracting PDF layout structure: {str(ex)}",
            )
        raise ex
    finally:
        doc.close()

    end_time = time.time()
    processing_time = round(end_time - start_time, 2)
    logger.info("PDF extraction completed in {} seconds. Status: {}", processing_time, status_str)

    return DocumentExtractionResult(
        upload_id=upload_id,
        status=status_str,
        metadata=doc_metadata,
        pages=canonical_pages,
        blocks=canonical_blocks,
        tables=canonical_tables,
        images=canonical_images,
        extraction_version="1.0.0",
        extraction_timestamp=datetime.now(timezone.utc).isoformat(),
        processing_time=processing_time,
    )
