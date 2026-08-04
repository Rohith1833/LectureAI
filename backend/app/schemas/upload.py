from pydantic import BaseModel


class UploadResponseData(BaseModel):
    """Metadata payload returned for a successful file upload."""

    upload_id: str
    original_filename: str
    stored_filename: str
    size_bytes: int
    mime_type: str
    uploaded_at: str
    status: str


class UploadResponse(BaseModel):
    """Standardized successful upload wrapper model."""

    success: bool
    message: str
    data: UploadResponseData
