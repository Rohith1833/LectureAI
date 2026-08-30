import time
from typing import Any, Dict, List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.knowledge import KnowledgeVersion
from app.models.conversation import Conversation, ConversationMessage


class ConversationRepository:
    """Repository managing lifecycle and persistence for Conversations."""

    def __init__(self, db: Session):
        self.db = db

    def create_conversation(
        self,
        document_id: str,
        knowledge_version_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Conversation:
        """
        Creates a new conversation session scoped to a document and optional knowledge version.
        Validates document existence and ensures knowledge version matches the document upload scope.
        """
        doc = self.db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError(f"Document with ID '{document_id}' does not exist.")

        if knowledge_version_id is not None:
            kv = (
                self.db.query(KnowledgeVersion)
                .filter(KnowledgeVersion.id == knowledge_version_id)
                .first()
            )
            if not kv:
                raise ValueError(
                    f"KnowledgeVersion with ID '{knowledge_version_id}' does not exist."
                )
            if kv.upload_id != doc.upload_id:
                raise ValueError(
                    f"KnowledgeVersion '{knowledge_version_id}' does not belong to Document '{document_id}'."
                )

        normalized_title = title.strip() if title and title.strip() else "New Conversation"
        now = time.time()

        conversation = Conversation(
            document_id=document_id,
            knowledge_version_id=knowledge_version_id,
            title=normalized_title,
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Fetches a conversation by ID."""
        return (
            self.db.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .first()
        )

    def list_conversations(
        self,
        document_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Conversation]:
        """Lists conversations for a document ordered by updated_at descending."""
        query = self.db.query(Conversation).filter(Conversation.document_id == document_id)
        if status is not None:
            query = query.filter(Conversation.status == status)

        return (
            query.order_by(Conversation.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def update_conversation(
        self,
        conversation_id: str,
        title: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[Conversation]:
        """Updates title and/or status of a conversation."""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            return None

        if title is not None:
            normalized = title.strip()
            if not normalized:
                raise ValueError("Conversation title cannot be empty.")
            conversation.title = normalized

        if status is not None:
            if status not in ("ACTIVE", "ARCHIVED"):
                raise ValueError(f"Invalid conversation status: '{status}'.")
            conversation.status = status

        conversation.updated_at = time.time()
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def archive_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Archives an active conversation."""
        return self.update_conversation(conversation_id, status="ARCHIVED")

    def delete_conversation(self, conversation_id: str) -> bool:
        """Deletes a conversation and its messages without affecting academic knowledge data."""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            return False

        self.db.delete(conversation)
        self.db.commit()
        return True


class MessageRepository:
    """Repository managing append-only persistence and ordered retrieval for ConversationMessages."""

    def __init__(self, db: Session):
        self.db = db

    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> ConversationMessage:
        """
        Appends an immutable message to a conversation with strict sequence ordering.
        Rejects empty content and writes to archived conversations.
        """
        conversation = (
            self.db.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .first()
        )
        if not conversation:
            raise ValueError(f"Conversation with ID '{conversation_id}' does not exist.")

        if conversation.status == "ARCHIVED":
            raise ValueError(f"Cannot append message to ARCHIVED conversation '{conversation_id}'.")

        if role not in ("USER", "ASSISTANT"):
            raise ValueError(f"Invalid message role '{role}'. Must be USER or ASSISTANT.")

        normalized_content = content.strip() if content else ""
        if not normalized_content:
            raise ValueError("Message content cannot be empty or whitespace-only.")

        # Compute next deterministic sequence number
        max_seq = (
            self.db.query(func.coalesce(func.max(ConversationMessage.sequence), 0))
            .filter(ConversationMessage.conversation_id == conversation_id)
            .scalar()
        )
        next_seq = max_seq + 1
        now = time.time()

        message = ConversationMessage(
            conversation_id=conversation_id,
            role=role,
            content=normalized_content,
            sequence=next_seq,
            created_at=now,
            metadata_json=metadata_json,
        )
        self.db.add(message)

        # Update conversation touch timestamp
        conversation.updated_at = now

        self.db.commit()
        self.db.refresh(message)
        return message

    def get_message(self, message_id: str) -> Optional[ConversationMessage]:
        """Fetches a single message by ID."""
        return (
            self.db.query(ConversationMessage)
            .filter(ConversationMessage.id == message_id)
            .first()
        )

    def list_messages(
        self,
        conversation_id: str,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[ConversationMessage]:
        """Retrieves ordered message history (ascending sequence) with optional pagination."""
        query = (
            self.db.query(ConversationMessage)
            .filter(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.sequence.asc())
            .offset(offset)
        )
        if limit is not None:
            query = query.limit(limit)

        return query.all()

    def count_messages(self, conversation_id: str) -> int:
        """Counts total messages in a conversation."""
        return (
            self.db.query(func.count(ConversationMessage.id))
            .filter(ConversationMessage.conversation_id == conversation_id)
            .scalar()
        )
