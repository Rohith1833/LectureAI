from enum import Enum
from typing import List, Optional
from pydantic import BaseModel


class BlockType(str, Enum):
    """Strongly-typed enums representing layouts element categories."""

    HEADING = "HEADING"
    PARAGRAPH = "PARAGRAPH"
    LIST = "LIST"
    TABLE = "TABLE"
    IMAGE = "IMAGE"
    EQUATION = "EQUATION"
    CAPTION = "CAPTION"
    HEADER = "HEADER"
    FOOTER = "FOOTER"
    FOOTNOTE = "FOOTNOTE"
    PAGE_NUMBER = "PAGE_NUMBER"
    QUOTE = "QUOTE"
    NOTE = "NOTE"
    CODE = "CODE"
    UNKNOWN = "UNKNOWN"


class BoundingBox(BaseModel):
    """Bounding coordinates [x0, y0, x1, y1] for elements inside a PDF page."""

    x0: float
    y0: float
    x1: float
    y1: float


class DocumentMetadataSchema(BaseModel):
    """Standard PDF metadata parameters."""

    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    keywords: Optional[str] = None
    creation_date: Optional[str] = None
    producer: Optional[str] = None
    page_count: int
    pdf_version: Optional[str] = None
    language: Optional[str] = None


class PageSchema(BaseModel):
    """Metadata detailing individual page index boundaries."""

    page_number: int
    width: float
    height: float


class BlockSchema(BaseModel):
    """Representing individual text segment blocks with style and layout pointers."""

    block_id: str
    page_number: int
    reading_order: int
    block_type: BlockType
    bounding_box: BoundingBox
    text: str
    font_size: Optional[float] = None
    font_family: Optional[str] = None
    bold: bool = False
    italic: bool = False
    confidence: float = 1.0
    parent_block_id: Optional[str] = None
    previous_block_id: Optional[str] = None
    next_block_id: Optional[str] = None
    heading_level: Optional[int] = None  # 1 to 6 (H1 to H6)
    extra_metadata: Optional[dict] = None
    provenance: str = "NATIVE"  # "NATIVE", "OCR", "MERGED"


class TableSchema(BaseModel):
    """Canonical model for extracted tabular grids."""

    table_id: str
    page_number: int
    bounding_box: BoundingBox
    rows_count: int
    columns_count: int
    data: List[List[str]]  # cell grid array


class ImageSchema(BaseModel):
    """Canonical model for registered visual elements."""

    image_id: str
    page_number: int
    bounding_box: BoundingBox
    width: float
    height: float
    caption: Optional[str] = None


class DocumentExtractionResult(BaseModel):
    """The Agnostic Canonical Document Model sitting between extraction & database layers."""

    upload_id: str
    status: str  # "processed" or "needs_ocr"
    metadata: DocumentMetadataSchema
    pages: List[PageSchema]
    blocks: List[BlockSchema]
    tables: List[TableSchema]
    images: List[ImageSchema]
    extraction_version: str = "1.0.0"
    extraction_timestamp: str
    processing_time: float
    ocr_status: Optional[str] = None
    ocr_engine: Optional[str] = None
    ocr_version: Optional[str] = None
    ocr_confidence: Optional[float] = None
    ocr_language: Optional[str] = None
    ocr_processing_time: Optional[float] = None
    extra_metadata: Optional[dict] = None
