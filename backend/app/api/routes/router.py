from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.api.routes.upload import router as upload_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.documents import router as documents_router

api_router = APIRouter()

api_router.include_router(health_router, tags=["Health"])
api_router.include_router(upload_router, tags=["Upload"])
api_router.include_router(jobs_router, tags=["Jobs"])
api_router.include_router(documents_router, tags=["Documents"])
