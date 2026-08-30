import uuid
from datetime import datetime
from typing import Any, Dict

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.dialects.postgresql import JSONB

from app.models.document import Base
from app.schemas.artifact import ArtifactStatus

class ArtifactJob(Base):
    __tablename__ = "artifact_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_id = Column(String, nullable=False, index=True)
    knowledge_version_id = Column(String, ForeignKey("knowledge_versions.id"), nullable=False, index=True)
    artifact_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default=ArtifactStatus.PENDING.value)
    
    # Store settings as JSON.
    config = Column(JSON, nullable=False, default=dict)
    plan = Column(JSON, nullable=True)
    
    artifact_uri = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
