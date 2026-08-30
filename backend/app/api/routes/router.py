from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.api.routes.upload import router as upload_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.documents import router as documents_router
from app.api.routes.review import router as review_router
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.retrieval import router as retrieval_router
from app.api.routes.generation import router as generation_router
from app.api.routes.conversation import router as conversation_router
from app.api.routes.artifact import router as artifact_router

api_router = APIRouter()

api_router.include_router(health_router, tags=["Health"])
api_router.include_router(upload_router, tags=["Upload"])
api_router.include_router(jobs_router, tags=["Jobs"])
api_router.include_router(documents_router, tags=["Documents"])
api_router.include_router(review_router, tags=["Review"])
api_router.include_router(knowledge_router, tags=["Knowledge"])
api_router.include_router(retrieval_router, tags=["Retrieval"])
api_router.include_router(generation_router, tags=["Generation"])
api_router.include_router(conversation_router, tags=["Conversations"])
api_router.include_router(artifact_router, prefix="/artifacts", tags=["Artifacts"])
