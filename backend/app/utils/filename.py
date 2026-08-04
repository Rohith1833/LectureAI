import uuid


def generate_stored_filename(original_filename: str) -> str:
    """Generate a unique stored filename using UUID, keeping the extension."""
    ext = "pdf"
    if "." in original_filename:
        ext = original_filename.split(".")[-1].lower()
    return f"{uuid.uuid4()}.{ext}"


def generate_upload_id() -> str:
    """Generate a unique upload ID."""
    return str(uuid.uuid4())
