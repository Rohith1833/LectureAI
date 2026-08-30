import time
import uuid
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    ForeignKey,
    Text,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.models.document import Base


class Conversation(Base):
    """Represents a conversation session scoped to a specific document and optional knowledge version."""
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    knowledge_version_id = Column(
        String(36),
        ForeignKey("knowledge_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title = Column(String(256), nullable=False, default="New Conversation")
    status = Column(String(32), default="ACTIVE", nullable=False, index=True)
    created_at = Column(Float, default=lambda: time.time(), nullable=False)
    updated_at = Column(Float, default=lambda: time.time(), nullable=False)

    # Relationships
    document = relationship("Document", back_populates="conversations")
    knowledge_version = relationship("KnowledgeVersion")
    messages = relationship(
        "ConversationMessage",
        back_populates="conversation",
        order_by="ConversationMessage.sequence",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ConversationMessage(Base):
    """Represents an ordered, immutable message entry within a conversation session."""
    __tablename__ = "conversation_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(
        String(36),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(32), nullable=False)  # USER or ASSISTANT
    content = Column(Text, nullable=False)
    sequence = Column(Integer, nullable=False)
    created_at = Column(Float, default=lambda: time.time(), nullable=False)
    metadata_json = Column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence", name="uq_conv_msg_sequence"),
    )

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
