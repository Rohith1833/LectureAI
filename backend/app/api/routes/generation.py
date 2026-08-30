"""
Generation API router — Phase 8D

Exposes:
    POST /api/v1/generation/query

Accepts a GenerationRequest, runs the full grounded Q&A pipeline, and
returns a GenerationResult.

The endpoint is async to allow the LLM provider call (GroqProvider) to be
properly awaited without blocking the ASGI event loop.

Provider selection:
    - If GROQ_API_KEY is configured and is not the test stub, GroqProvider
      is used.
    - Otherwise MockLLMProvider(scenario="success") is used with a warning,
      appropriate for local development without a real key.

Error mapping:
    ValueError (not found)   → 404
    ValueError (other)       → 400
    LLMProviderError         → 502
    GroundingValidationError → 422
    Unhandled                → 500 (global handler in main.py)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.repositories.conversation_repository import (
    ConversationRepository,
    MessageRepository,
)
from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.schemas.generation import GenerationRequest, GenerationResult
from app.services.generation.base import LLMProvider
from app.services.generation.errors import GroundingValidationError, LLMProviderError
from app.services.generation.generation_service import GenerationService
from app.services.generation.groq_provider import GroqProvider
from app.services.generation.mock_provider import MockLLMProvider
from app.services.retrieval.retrieval_service import RetrievalService

router = APIRouter(prefix="/generation", tags=["Generation"])


def _get_provider() -> LLMProvider:
    """
    Select the active LLM provider from environment configuration.

    Returns GroqProvider when a real (non-stub) API key is present.
    Falls back to MockLLMProvider for local development without a key,
    emitting a warning so the developer is clearly informed.
    """
    key = settings.GROQ_API_KEY
    if key and key.strip() and key.strip() != "test-groq-key":
        logger.debug("GenerationRouter: using GroqProvider (model='{}')", settings.GROQ_MODEL)
        return GroqProvider()

    logger.warning(
        "GenerationRouter: GROQ_API_KEY not configured or is test stub — "
        "using MockLLMProvider. Set GROQ_API_KEY in .env for real generation."
    )
    return MockLLMProvider(scenario="success")


@router.post("/query", response_model=GenerationResult)
async def query_generation(
    request: GenerationRequest,
    db: Session = Depends(get_db),
) -> GenerationResult:
    """
    Execute the complete grounded Q&A pipeline.

    Accepts a GenerationRequest containing a user query, a RetrievalScope
    (document + optional version), retrieval options, generation options,
    and optional conversation_id.

    Returns a GenerationResult containing:
        - Grounded natural-language answer
        - Validated claims with per-claim grounding status
        - Citations mapped from GenerationContext sources
        - Overall grounding status
        - Model metadata (model name, token usage)
    """
    repo = KnowledgeRepository(db)
    doc_repo = DocumentRepository(db)
    conv_repo = ConversationRepository(db)
    msg_repo = MessageRepository(db)
    retrieval_service = RetrievalService(repo, doc_repo)
    provider = _get_provider()

    service = GenerationService(
        retrieval_service=retrieval_service,
        provider=provider,
        conversation_repo=conv_repo,
        message_repo=msg_repo,
    )

    try:
        return await service.generate(request)

    except ValueError as e:
        msg = str(e)
        if "archived" in msg.lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
        if "not found" in msg.lower() or "does not exist" in msg.lower() or "no finalized" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    except LLMProviderError as e:
        logger.error("GenerationRouter: LLMProviderError — {}", str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI service error: {str(e)}",
        )

    except GroundingValidationError as e:
        logger.warning("GenerationRouter: GroundingValidationError — {}", str(e))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"AI response validation failed: {str(e)}",
        )
