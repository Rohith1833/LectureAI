import json
import os
from datetime import datetime, timezone
from fastapi import UploadFile, HTTPException, status
from loguru import logger

from app.schemas.upload import UploadResponse, UploadResponseData
from app.utils.filename import generate_stored_filename, generate_upload_id
from app.utils.file_validation import (
    validate_file_metadata,
    validate_magic_bytes,
    MAX_FILE_SIZE_BYTES,
)

from app.core.storage import UPLOADS_DIR, METADATA_DIR


async def process_and_store_upload(file: UploadFile) -> UploadResponse:
    """Validate, stream upload stream to disk in chunks, and persist metadata."""
    # 1. Check metadata (name, MIME type, extension)
    validate_file_metadata(file.filename, file.content_type)

    logger.info("Upload started for file: {}", file.filename)

    # 2. Read first chunk to validate magic bytes (header signature)
    # Read first 1KB of content
    first_chunk = await file.read(1024)
    validate_magic_bytes(first_chunk)

    # 3. Generate distinct IDs and file buffer parameters
    upload_id = generate_upload_id()
    # file.filename has been verified as present during validate_file_metadata
    stored_name = generate_stored_filename(file.filename or "file.pdf")
    stored_path = os.path.join(UPLOADS_DIR, stored_name)

    total_size = len(first_chunk)

    try:
        with open(stored_path, "wb") as buffer:
            # Write first read chunk
            buffer.write(first_chunk)

            # Stream remaining content in 1MB chunks to disk
            chunk_size = 1024 * 1024  # 1 MB
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break

                total_size += len(chunk)
                if total_size > MAX_FILE_SIZE_BYTES:
                    logger.warning("Upload failed: File exceeds limit. Size: {} bytes", total_size)
                    buffer.close()
                    if os.path.exists(stored_path):
                        os.remove(stored_path)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="File exceeds maximum allowed size of 100 MB.",
                    )
                buffer.write(chunk)

        # 4. Check for empty files
        if total_size == 0:
            logger.warning("Upload failed: Empty payload received.")
            if os.path.exists(stored_path):
                os.remove(stored_path)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty.",
            )

    except Exception as e:
        if not isinstance(e, HTTPException):
            logger.error("Storage failure while saving file: {}", str(e))
            if os.path.exists(stored_path):
                os.remove(stored_path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save uploaded file to disk.",
            )
        raise e

    # 5. Compile metadata payload
    uploaded_at = datetime.now(timezone.utc).isoformat()
    metadata_payload = {
        "upload_id": upload_id,
        "original_filename": file.filename or "file.pdf",
        "stored_filename": stored_name,
        "size_bytes": total_size,
        "mime_type": file.content_type or "application/pdf",
        "uploaded_at": uploaded_at,
        "status": "uploaded",
    }

    # Persist metadata to JSON file
    metadata_path = os.path.join(METADATA_DIR, f"{upload_id}.json")
    try:
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata_payload, f, indent=2)
    except Exception as e:
        logger.error("Storage failure saving metadata: {}", str(e))
        if os.path.exists(stored_path):
            os.remove(stored_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save upload metadata to disk.",
        )

    logger.info("Upload completed successfully. ID: {}, Saved Path: {}", upload_id, stored_path)

    # Return standard successful upload wrapper
    return UploadResponse(
        success=True,
        message="Upload successful",
        data=UploadResponseData(**metadata_payload),
    )
