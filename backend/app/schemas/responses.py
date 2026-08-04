from pydantic import BaseModel


class HealthData(BaseModel):
    """Inner data for health response."""

    status: str


class HealthResponse(BaseModel):
    """Response schema for the health endpoint."""

    success: bool
    message: str
    data: HealthData


class RootResponse(BaseModel):
    """Response schema for the root endpoint."""

    project: str
    version: str


class ErrorDetail(BaseModel):
    """Detailed explanation of a single field error."""

    field: str
    message: str


class ErrorResponse(BaseModel):
    """Standardized error response schema."""

    success: bool
    message: str
    errors: list[ErrorDetail]

