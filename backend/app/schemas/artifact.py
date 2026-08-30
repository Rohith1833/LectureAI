from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

class ArtifactStatus(str, Enum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    RENDERING = "RENDERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class ArtifactType(str, Enum):
    PPTX = "PPTX"

class SlideType(str, Enum):
    TITLE = "TITLE"
    CONTENT = "CONTENT"
    CONCEPT = "CONCEPT"
    EXAMPLE = "EXAMPLE"
    QUESTION = "QUESTION"

class SlideModel(BaseModel):
    slide_type: SlideType
    title: str
    content: List[str] = Field(default_factory=list)
    speaker_notes: str = ""
    source_node_ids: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)

class ArtifactPlan(BaseModel):
    slides: List[SlideModel] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ArtifactJobCreate(BaseModel):
    upload_id: str
    knowledge_version_id: str
    artifact_type: ArtifactType = ArtifactType.PPTX
    config: Dict[str, Any] = Field(default_factory=dict)

class ArtifactJobRead(BaseModel):
    id: str
    upload_id: str
    knowledge_version_id: str
    artifact_type: ArtifactType
    status: ArtifactStatus
    config: Dict[str, Any]
    artifact_uri: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True
