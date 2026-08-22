from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.document import (
    Document,
    DocumentMetadata,
    DocumentPage,
    DocumentBlock,
    DocumentTable,
    DocumentImage,
)
from app.schemas.document import DocumentExtractionResult


class DocumentRepository:
    """Repository managing ORM mappings and queries for the Document Extraction Result."""

    def __init__(self, db: Session):
        self.db = db

    def save_extraction_result(self, result: DocumentExtractionResult) -> Document:
        """Atomically persist a Canonical Document Extraction Result into the DB."""
        # 1. Create base document ORM entry
        db_doc = Document(
            upload_id=result.upload_id,
            status=result.status,
            extraction_version=result.extraction_version,
            extraction_timestamp=result.extraction_timestamp,
            processing_time=result.processing_time,
            ocr_status=result.ocr_status,
            ocr_engine=result.ocr_engine,
            ocr_version=result.ocr_version,
            ocr_confidence=result.ocr_confidence,
            ocr_language=result.ocr_language,
            ocr_processing_time=result.ocr_processing_time,
            extra_metadata=result.extra_metadata,
        )
        self.db.add(db_doc)
        self.db.flush()  # Populates db_doc.id

        # 2. Persist DocumentMetadata
        meta = result.metadata
        db_meta = DocumentMetadata(
            document_id=db_doc.id,
            title=meta.title,
            author=meta.author,
            subject=meta.subject,
            keywords=meta.keywords,
            creation_date=meta.creation_date,
            producer=meta.producer,
            page_count=meta.page_count,
            pdf_version=meta.pdf_version,
            language=meta.language,
        )
        self.db.add(db_meta)

        # 3. Persist Pages and track page index mappings
        page_num_to_id = {}
        for p in result.pages:
            db_page = DocumentPage(
                document_id=db_doc.id,
                page_number=p.page_number,
                width=p.width,
                height=p.height,
            )
            self.db.add(db_page)
            self.db.flush()  # Populates db_page.id
            page_num_to_id[p.page_number] = db_page.id

        # 4. Persist Blocks
        for b in result.blocks:
            page_id = page_num_to_id[b.page_number]
            db_block = DocumentBlock(
                id=b.block_id,
                document_id=db_doc.id,
                page_id=page_id,
                page_number=b.page_number,
                reading_order=b.reading_order,
                block_type=b.block_type.value,
                text=b.text,
                x0=b.bounding_box.x0,
                y0=b.bounding_box.y0,
                x1=b.bounding_box.x1,
                y1=b.bounding_box.y1,
                font_size=b.font_size,
                font_family=b.font_family,
                bold=b.bold,
                italic=b.italic,
                confidence=b.confidence,
                parent_block_id=b.parent_block_id,
                previous_block_id=b.previous_block_id,
                next_block_id=b.next_block_id,
                heading_level=b.heading_level,
                extra_metadata=b.extra_metadata,
                provenance=b.provenance,
            )
            self.db.add(db_block)

        # 5. Persist Tables
        for t in result.tables:
            page_id = page_num_to_id[t.page_number]
            db_table = DocumentTable(
                id=t.table_id,
                document_id=db_doc.id,
                page_id=page_id,
                page_number=t.page_number,
                x0=t.bounding_box.x0,
                y0=t.bounding_box.y0,
                x1=t.bounding_box.x1,
                y1=t.bounding_box.y1,
                rows_count=t.rows_count,
                columns_count=t.columns_count,
                data=t.data,
            )
            self.db.add(db_table)

        # 6. Persist Images
        for img in result.images:
            page_id = page_num_to_id[img.page_number]
            db_img = DocumentImage(
                id=img.image_id,
                document_id=db_doc.id,
                page_id=page_id,
                page_number=img.page_number,
                x0=img.bounding_box.x0,
                y0=img.bounding_box.y0,
                x1=img.bounding_box.x1,
                y1=img.bounding_box.y1,
                width=img.width,
                height=img.height,
                caption=img.caption,
            )
            self.db.add(db_img)

        self.db.commit()
        return db_doc

    def get_document_by_upload_id(self, upload_id: str) -> Optional[Document]:
        """Fetch document model by its upload ID."""
        return self.db.query(Document).filter(Document.upload_id == upload_id).first()

    def get_document(self, document_id: str) -> Optional[Document]:
        """Fetch document model by primary ID."""
        return self.db.query(Document).filter(Document.id == document_id).first()

    def get_blocks_for_page(self, document_id: str, page_number: int) -> List[DocumentBlock]:
        """Fetch all blocks for a specific page of a document, ordered by reading_order."""
        return (
            self.db.query(DocumentBlock)
            .filter(
                DocumentBlock.document_id == document_id,
                DocumentBlock.page_number == page_number
            )
            .order_by(DocumentBlock.reading_order.asc())
            .all()
        )

    def get_block(self, block_id: str) -> Optional[DocumentBlock]:
        """Fetch a specific DocumentBlock by its primary ID."""
        return self.db.query(DocumentBlock).filter(DocumentBlock.id == block_id).first()

