from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.document_repository import DocumentRepository

router = APIRouter()


@router.get("/documents/{id}")
async def get_document_by_id(id: str, db: Session = Depends(get_db)):
    """Fetch details and metadata of an extracted document by its primary ID."""
    repo = DocumentRepository(db)
    doc = repo.get_document(id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    return {
        "success": True,
        "data": {
            "id": doc.id,
            "upload_id": doc.upload_id,
            "status": doc.status,
            "extraction_version": doc.extraction_version,
            "extraction_timestamp": doc.extraction_timestamp,
            "processing_time": doc.processing_time,
            "metadata": {
                "title": doc.metadata_rel.title if doc.metadata_rel else None,
                "author": doc.metadata_rel.author if doc.metadata_rel else None,
                "subject": doc.metadata_rel.subject if doc.metadata_rel else None,
                "keywords": doc.metadata_rel.keywords if doc.metadata_rel else None,
                "creation_date": doc.metadata_rel.creation_date if doc.metadata_rel else None,
                "producer": doc.metadata_rel.producer if doc.metadata_rel else None,
                "page_count": doc.metadata_rel.page_count if doc.metadata_rel else 0,
                "pdf_version": doc.metadata_rel.pdf_version if doc.metadata_rel else None,
                "language": doc.metadata_rel.language if doc.metadata_rel else None,
            },
        },
    }


@router.get("/documents/upload/{upload_id}")
async def get_document_by_upload_id(upload_id: str, db: Session = Depends(get_db)):
    """Fetch details and metadata of an extracted document by its source upload ID."""
    repo = DocumentRepository(db)
    doc = repo.get_document_by_upload_id(upload_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found for this upload ID.",
        )

    return {
        "success": True,
        "data": {
            "id": doc.id,
            "upload_id": doc.upload_id,
            "status": doc.status,
            "extraction_version": doc.extraction_version,
            "extraction_timestamp": doc.extraction_timestamp,
            "processing_time": doc.processing_time,
            "metadata": {
                "title": doc.metadata_rel.title if doc.metadata_rel else None,
                "author": doc.metadata_rel.author if doc.metadata_rel else None,
                "subject": doc.metadata_rel.subject if doc.metadata_rel else None,
                "keywords": doc.metadata_rel.keywords if doc.metadata_rel else None,
                "creation_date": doc.metadata_rel.creation_date if doc.metadata_rel else None,
                "producer": doc.metadata_rel.producer if doc.metadata_rel else None,
                "page_count": doc.metadata_rel.page_count if doc.metadata_rel else 0,
                "pdf_version": doc.metadata_rel.pdf_version if doc.metadata_rel else None,
                "language": doc.metadata_rel.language if doc.metadata_rel else None,
            },
        },
    }


@router.get("/documents/{id}/pages")
async def get_document_pages(id: str, db: Session = Depends(get_db)):
    """Retrieve list of pages for a specific document."""
    repo = DocumentRepository(db)
    doc = repo.get_document(id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    pages = [
        {
            "id": p.id,
            "page_number": p.page_number,
            "width": p.width,
            "height": p.height,
        }
        for p in doc.pages
    ]

    return {"success": True, "data": pages}


@router.get("/documents/{id}/blocks")
async def get_document_blocks(id: str, db: Session = Depends(get_db)):
    """Retrieve all layout blocks, table cells, and images associated with a document."""
    repo = DocumentRepository(db)
    doc = repo.get_document(id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    # Sort text blocks by page number and reading order index
    sorted_blocks = sorted(doc.blocks, key=lambda b: (b.page_number, b.reading_order))

    blocks_data = [
        {
            "block_id": b.id,
            "page_number": b.page_number,
            "reading_order": b.reading_order,
            "block_type": b.block_type,
            "text": b.text,
            "bounding_box": {
                "x0": b.x0,
                "y0": b.y0,
                "x1": b.x1,
                "y1": b.y1,
            },
            "font_size": b.font_size,
            "font_family": b.font_family,
            "bold": b.bold,
            "italic": b.italic,
            "confidence": b.confidence,
            "parent_block_id": b.parent_block_id,
            "previous_block_id": b.previous_block_id,
            "next_block_id": b.next_block_id,
            "heading_level": b.heading_level,
        }
        for b in sorted_blocks
    ]

    tables_data = [
        {
            "table_id": t.id,
            "page_number": t.page_number,
            "rows_count": t.rows_count,
            "columns_count": t.columns_count,
            "bounding_box": {
                "x0": t.x0,
                "y0": t.y0,
                "x1": t.x1,
                "y1": t.y1,
            },
            "data": t.data,
        }
        for t in doc.tables
    ]

    images_data = [
        {
            "image_id": img.id,
            "page_number": img.page_number,
            "width": img.width,
            "height": img.height,
            "bounding_box": {
                "x0": img.x0,
                "y0": img.y0,
                "x1": img.x1,
                "y1": img.y1,
            },
            "caption": img.caption,
        }
        for img in doc.images
    ]

    return {
        "success": True,
        "data": {"blocks": blocks_data, "tables": tables_data, "images": images_data},
    }


@router.get("/documents/{id}/statistics")
async def get_document_statistics(id: str, db: Session = Depends(get_db)):
    """Generate high-level metadata extraction statistics for developers preview checks."""
    repo = DocumentRepository(db)
    doc = repo.get_document(id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    # Word count heuristic
    word_count = sum(len(b.text.split()) for b in doc.blocks)

    heading_count = sum(1 for b in doc.blocks if b.block_type == "HEADING")
    paragraph_count = sum(1 for b in doc.blocks if b.block_type == "PARAGRAPH")
    list_count = sum(1 for b in doc.blocks if b.block_type == "LIST")

    return {
        "success": True,
        "data": {
            "page_count": len(doc.pages),
            "word_count": word_count,
            "images_count": len(doc.images),
            "tables_count": len(doc.tables),
            "headings_count": heading_count,
            "paragraphs_count": paragraph_count,
            "lists_count": list_count,
        },
    }
