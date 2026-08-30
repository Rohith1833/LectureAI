"""
Conversation API Router — Phase 8G-3

Exposes endpoints for conversation lifecycle and message history:
- POST /api/v1/documents/{document_id}/conversations
- GET  /api/v1/documents/{document_id}/conversations
- GET  /api/v1/conversations/{conversation_id}
- PATCH /api/v1/conversations/{conversation_id}
- POST /api/v1/conversations/{conversation_id}/archive
- GET  /api/v1/conversations/{conversation_id}/messages
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.conversation_repository import (
    ConversationRepository,
    MessageRepository,
)
from app.schemas.conversation import (
    ConversationCreatePayload,
    ConversationRead,
    ConversationStatus,
    ConversationUpdate,
    MessageRead,
)

router = APIRouter(tags=["Conversations"])


# -----------------------------------------------------------------------------
# Document-Scoped Conversation Endpoints
# -----------------------------------------------------------------------------

@router.post(
    "/documents/{document_id}/conversations",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new conversation for a document",
)
def create_document_conversation(
    document_id: str,
    payload: Optional[ConversationCreatePayload] = None,
    db: Session = Depends(get_db),
) -> ConversationRead:
    """Create a new conversational session scoped to a specific document and optional knowledge version."""
    conv_repo = ConversationRepository(db)
    msg_repo = MessageRepository(db)

    version_id = payload.knowledge_version_id if payload else None
    title = payload.title if payload else None

    try:
        conv = conv_repo.create_conversation(
            document_id=document_id,
            knowledge_version_id=version_id,
            title=title,
        )
        count = msg_repo.count_messages(conv.id)
        return ConversationRead(
            id=conv.id,
            document_id=conv.document_id,
            knowledge_version_id=conv.knowledge_version_id,
            title=conv.title,
            status=ConversationStatus(conv.status),
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=count,
        )
    except ValueError as e:
        msg = str(e)
        logger.warning("Failed to create conversation: {}", msg)
        if "not found" in msg.lower() or "does not exist" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.get(
    "/documents/{document_id}/conversations",
    response_model=List[ConversationRead],
    summary="List conversations for a document",
)
def list_document_conversations(
    document_id: str,
    status_filter: Optional[ConversationStatus] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> List[ConversationRead]:
    """List all conversations for a document ordered by updated_at descending."""
    conv_repo = ConversationRepository(db)
    msg_repo = MessageRepository(db)

    status_val = status_filter.value if status_filter else None
    conversations = conv_repo.list_conversations(
        document_id=document_id,
        status=status_val,
        limit=limit,
        offset=offset,
    )

    results = []
    for conv in conversations:
        count = msg_repo.count_messages(conv.id)
        results.append(
            ConversationRead(
                id=conv.id,
                document_id=conv.document_id,
                knowledge_version_id=conv.knowledge_version_id,
                title=conv.title,
                status=ConversationStatus(conv.status),
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                message_count=count,
            )
        )
    return results


# -----------------------------------------------------------------------------
# Conversation Entity Endpoints
# -----------------------------------------------------------------------------

@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationRead,
    summary="Get conversation metadata",
)
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
) -> ConversationRead:
    """Retrieve metadata for a single conversation."""
    conv_repo = ConversationRepository(db)
    msg_repo = MessageRepository(db)

    conv = conv_repo.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' does not exist.",
        )

    count = msg_repo.count_messages(conv.id)
    return ConversationRead(
        id=conv.id,
        document_id=conv.document_id,
        knowledge_version_id=conv.knowledge_version_id,
        title=conv.title,
        status=ConversationStatus(conv.status),
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=count,
    )


@router.patch(
    "/conversations/{conversation_id}",
    response_model=ConversationRead,
    summary="Update conversation metadata",
)
def update_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    db: Session = Depends(get_db),
) -> ConversationRead:
    """Update title or status of a conversation."""
    conv_repo = ConversationRepository(db)
    msg_repo = MessageRepository(db)

    status_val = payload.status.value if payload.status else None

    try:
        conv = conv_repo.update_conversation(
            conversation_id=conversation_id,
            title=payload.title,
            status=status_val,
        )
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation '{conversation_id}' does not exist.",
            )

        count = msg_repo.count_messages(conv.id)
        return ConversationRead(
            id=conv.id,
            document_id=conv.document_id,
            knowledge_version_id=conv.knowledge_version_id,
            title=conv.title,
            status=ConversationStatus(conv.status),
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=count,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/conversations/{conversation_id}/archive",
    response_model=ConversationRead,
    summary="Archive a conversation",
)
def archive_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
) -> ConversationRead:
    """Transition a conversation to ARCHIVED status."""
    conv_repo = ConversationRepository(db)
    msg_repo = MessageRepository(db)

    conv = conv_repo.archive_conversation(conversation_id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' does not exist.",
        )

    count = msg_repo.count_messages(conv.id)
    return ConversationRead(
        id=conv.id,
        document_id=conv.document_id,
        knowledge_version_id=conv.knowledge_version_id,
        title=conv.title,
        status=ConversationStatus(conv.status),
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=count,
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=List[MessageRead],
    summary="List messages in a conversation",
)
def list_conversation_messages(
    conversation_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> List[MessageRead]:
    """Retrieve chronologically sorted messages for a conversation."""
    conv_repo = ConversationRepository(db)
    msg_repo = MessageRepository(db)

    conv = conv_repo.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' does not exist.",
        )

    messages = msg_repo.list_messages(
        conversation_id=conversation_id,
        limit=limit,
        offset=offset,
    )

    return [
        MessageRead(
            id=m.id,
            conversation_id=m.conversation_id,
            role=m.role,
            content=m.content,
            sequence=m.sequence,
            created_at=m.created_at,
            metadata_json=m.metadata_json,
        )
        for m in messages
    ]
