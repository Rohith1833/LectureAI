import uuid
from sqlalchemy import Column, String, Integer, Float, Boolean, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_id = Column(String(36), nullable=False, index=True)
    status = Column(String(32), default="processed")  # "processed" or "needs_ocr"
    review_state = Column(String(32), default="NEEDS_REVIEW", nullable=False)

    # Meta auditing info
    extraction_version = Column(String(32), default="1.0.0")
    extraction_timestamp = Column(String(64), nullable=False)
    processing_time = Column(Float, nullable=False)

    # OCR Auditing Info
    ocr_status = Column(String(32), nullable=True)  # "skipped", "completed", "failed"
    ocr_engine = Column(String(64), nullable=True)
    ocr_version = Column(String(32), nullable=True)
    ocr_confidence = Column(Float, nullable=True)
    ocr_language = Column(String(32), nullable=True)
    ocr_processing_time = Column(Float, nullable=True)

    # Future-proofing flexible extensions column
    extra_metadata = Column(JSON, nullable=True)

    # Cascading relationships
    metadata_rel = relationship(
        "DocumentMetadata",
        back_populates="document",
        uselist=False,
        cascade="all, delete-orphan",
    )
    pages = relationship(
        "DocumentPage",
        back_populates="document",
        order_by="DocumentPage.page_number",
        cascade="all, delete-orphan",
    )
    blocks = relationship("DocumentBlock", back_populates="document", cascade="all, delete-orphan")
    tables = relationship("DocumentTable", back_populates="document", cascade="all, delete-orphan")
    images = relationship("DocumentImage", back_populates="document", cascade="all, delete-orphan")


class DocumentMetadata(Base):
    __tablename__ = "document_metadata"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    title = Column(String(256), nullable=True)
    author = Column(String(256), nullable=True)
    subject = Column(String(256), nullable=True)
    keywords = Column(Text, nullable=True)
    creation_date = Column(String(64), nullable=True)
    producer = Column(String(128), nullable=True)
    page_count = Column(Integer, nullable=False)
    pdf_version = Column(String(32), nullable=True)
    language = Column(String(32), nullable=True)

    extra_metadata = Column(JSON, nullable=True)

    document = relationship("Document", back_populates="metadata_rel")


class DocumentPage(Base):
    __tablename__ = "document_pages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    page_number = Column(Integer, nullable=False, index=True)  # 1-indexed page
    width = Column(Float, nullable=False)
    height = Column(Float, nullable=False)

    extra_metadata = Column(JSON, nullable=True)

    document = relationship("Document", back_populates="pages")
    blocks = relationship("DocumentBlock", back_populates="page_rel", cascade="all, delete-orphan")


class DocumentBlock(Base):
    __tablename__ = "document_blocks"

    id = Column(String(36), primary_key=True)  # immutable block_id string
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    page_id = Column(String(36), ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False)

    page_number = Column(Integer, nullable=False)
    reading_order = Column(Integer, nullable=False)
    block_type = Column(String(32), nullable=False)  # Enums value e.g. HEADING, PARAGRAPH
    text = Column(Text, nullable=False)

    # Bounding Box Coordinates
    x0 = Column(Float, nullable=False)
    y0 = Column(Float, nullable=False)
    x1 = Column(Float, nullable=False)
    y1 = Column(Float, nullable=False)

    # Style details
    font_size = Column(Float, nullable=True)
    font_family = Column(String(128), nullable=True)
    bold = Column(Boolean, default=False)
    italic = Column(Boolean, default=False)
    confidence = Column(Float, default=1.0)
    provenance = Column(String(32), default="NATIVE")  # "NATIVE", "OCR", "MERGED"

    # Hierarchy Relations
    parent_block_id = Column(String(36), nullable=True)
    previous_block_id = Column(String(36), nullable=True)
    next_block_id = Column(String(36), nullable=True)
    heading_level = Column(Integer, nullable=True)  # heading depth H1-H6

    extra_metadata = Column(JSON, nullable=True)

    document = relationship("Document", back_populates="blocks")
    page_rel = relationship("DocumentPage", back_populates="blocks")


class DocumentTable(Base):
    __tablename__ = "document_tables"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    page_id = Column(String(36), ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False)

    page_number = Column(Integer, nullable=False)
    x0 = Column(Float, nullable=False)
    y0 = Column(Float, nullable=False)
    x1 = Column(Float, nullable=False)
    y1 = Column(Float, nullable=False)

    rows_count = Column(Integer, nullable=False)
    columns_count = Column(Integer, nullable=False)
    data = Column(JSON, nullable=False)  # grid matrix content representation

    extra_metadata = Column(JSON, nullable=True)

    document = relationship("Document", back_populates="tables")


class DocumentImage(Base):
    __tablename__ = "document_images"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    page_id = Column(String(36), ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False)

    page_number = Column(Integer, nullable=False)
    x0 = Column(Float, nullable=False)
    y0 = Column(Float, nullable=False)
    x1 = Column(Float, nullable=False)
    y1 = Column(Float, nullable=False)

    width = Column(Float, nullable=False)
    height = Column(Float, nullable=False)
    caption = Column(Text, nullable=True)

    extra_metadata = Column(JSON, nullable=True)

    document = relationship("Document", back_populates="images")
