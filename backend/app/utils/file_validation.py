from fastapi import HTTPException, status
from loguru import logger

MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB
ALLOWED_MIME_TYPE = "application/pdf"
ALLOWED_EXTENSION = ".pdf"
PDF_MAGIC_BYTES = b"%PDF-"


def validate_file_metadata(filename: str | None, content_type: str | None) -> None:
    """Validate file extension and MIME type before reading content."""
    if not filename:
        logger.warning("Validation failed: Missing filename.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file was uploaded.",
        )

    if not filename.lower().endswith(ALLOWED_EXTENSION):
        logger.warning("Validation failed: Invalid extension for '{}'.", filename)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are allowed.",
        )

    if content_type != ALLOWED_MIME_TYPE:
        logger.warning("Validation failed: Invalid MIME type '{}' for '{}'.", content_type, filename)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are allowed.",
        )


def validate_magic_bytes(first_chunk: bytes) -> None:
    """Validate the file's PDF header magic number (%PDF-)."""
    if len(first_chunk) < len(PDF_MAGIC_BYTES) or not first_chunk.startswith(PDF_MAGIC_BYTES):
        logger.warning("Validation failed: File header magic bytes did not match %PDF-.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file signature. The file is not a valid PDF document.",
        )
