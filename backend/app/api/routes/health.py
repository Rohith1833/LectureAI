from fastapi import APIRouter

from app.schemas.responses import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return the current health status of the backend."""
    return HealthResponse(
        success=True,
        message="LectureAI Backend Running",
        data={"status": "ok"},
    )
