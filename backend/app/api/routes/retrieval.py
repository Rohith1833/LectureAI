from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.schemas.retrieval import RetrievalRequest, RetrievalResult
from app.services.retrieval.retrieval_service import RetrievalService

router = APIRouter(prefix="/retrieval", tags=["Retrieval"])


@router.post("/query", response_model=RetrievalResult)
def query_retrieval(
    request: RetrievalRequest,
    db: Session = Depends(get_db)
) -> RetrievalResult:
    """
    Executes the retrieval pipeline over versioned knowledge models.
    Delegates completely to RetrievalService.
    """
    repo = KnowledgeRepository(db)
    doc_repo = DocumentRepository(db)
    service = RetrievalService(repo, doc_repo)
    try:
        return service.retrieve(request)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=msg
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=msg
            )
