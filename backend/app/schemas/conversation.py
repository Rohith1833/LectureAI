import time
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class ConversationStatus(str, Enum):
    """Lifecycle state of a conversation."""
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class MessageRole(str, Enum):
    """Sender role for a conversational message."""
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class ConversationCreatePayload(BaseModel):
    """Payload for creating a conversation under a document route."""
    knowledge_version_id: Optional[str] = Field(None, description="Optional target finalized knowledge version scope")
    title: Optional[str] = Field(None, max_length=256, description="Optional custom conversation title")

    @field_validator("title")
    @classmethod
    def normalize_title(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            return v if v else None
        return None


class ConversationCreate(BaseModel):
    """Input payload for creating a new conversation session."""
    document_id: str = Field(..., min_length=1, description="ID of the parent document")
    knowledge_version_id: Optional[str] = Field(None, description="Optional target finalized knowledge version scope")
    title: Optional[str] = Field(None, max_length=256, description="Optional custom conversation title")

    @field_validator("title")
    @classmethod
    def normalize_title(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            return v if v else None
        return None


class ConversationUpdate(BaseModel):
    """Payload for updating conversation metadata or status."""
    title: Optional[str] = Field(None, max_length=256)
    status: Optional[ConversationStatus] = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Conversation title cannot be empty.")
            return v
        return None


class MessageCreate(BaseModel):
    """Payload for appending a message to a conversation."""
    role: MessageRole = Field(..., description="Message author role: USER or ASSISTANT")
    content: str = Field(..., min_length=1, max_length=32768, description="Message text content")
    metadata_json: Optional[Dict[str, Any]] = Field(None, description="Optional message metadata")

    @field_validator("content")
    @classmethod
    def validate_content_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Message content cannot be empty or whitespace-only.")
        return v.strip()


class MessageRead(BaseModel):
    """Serialized message response contract."""
    id: str
    conversation_id: str
    role: MessageRole
    content: str
    sequence: int
    created_at: float
    metadata_json: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class ConversationRead(BaseModel):
    """Serialized conversation response contract."""
    id: str
    document_id: str
    knowledge_version_id: Optional[str] = None
    title: str
    status: ConversationStatus
    created_at: float
    updated_at: float
    message_count: int = 0
    messages: Optional[List[MessageRead]] = None

    class Config:
        from_attributes = True
