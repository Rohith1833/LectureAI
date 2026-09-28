from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

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

class ArtifactGenerationConfig(BaseModel):
    """
    Typed request configuration for artifact generation.
    Strictly validates container selection inputs while allowing unrelated presentation settings.
    """
    model_config = ConfigDict(extra="allow")

    selected_unit_ids: Optional[List[str]] = None
    num_units: Optional[int] = None
    include_examples: bool = True
    include_questions: bool = True
    audience_level: str = "general"
    depth: str = "standard"
    container_mode: Optional[str] = None
    container_type: Optional[str] = None
    document_id: Optional[str] = None

    @field_validator("selected_unit_ids", mode="before")
    @classmethod
    def validate_selected_unit_ids(cls, v: Any) -> Optional[List[str]]:
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError("'selected_unit_ids' must be a list of container IDs.")
        if len(v) == 0:
            raise ValueError("Explicit selection cannot be empty.")
        validated = []
        for i, elem in enumerate(v):
            if elem is None:
                raise ValueError(f"Element at index {i} in 'selected_unit_ids' cannot be null.")
            if not isinstance(elem, str):
                raise ValueError(f"Element at index {i} in 'selected_unit_ids' must be a string, got {type(elem).__name__}.")
            if not elem.strip():
                raise ValueError(f"Element at index {i} in 'selected_unit_ids' cannot be an empty string.")
            validated.append(elem)
        return validated

    @field_validator("num_units", mode="before")
    @classmethod
    def validate_num_units(cls, v: Any) -> Optional[int]:
        if v is None:
            return None
        if type(v) is bool:
            raise ValueError("'num_units' cannot be a boolean.")
        if not (type(v) is int):
            raise ValueError(f"'num_units' must be an integer, got {type(v).__name__}.")
        if v <= 0:
            raise ValueError(f"'num_units' must be a positive integer greater than zero, got {v}.")
        return v

    @model_validator(mode="after")
    def validate_mutual_exclusion(self) -> "ArtifactGenerationConfig":
        if self.selected_unit_ids is not None and self.num_units is not None:
            raise ValueError("Cannot specify both 'selected_unit_ids' and 'num_units'.")
        return self

class ArtifactJobCreate(BaseModel):
    upload_id: str
    knowledge_version_id: str
    artifact_type: ArtifactType = ArtifactType.PPTX
    config: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("config", mode="before")
    @classmethod
    def validate_config(cls, v: Any) -> Dict[str, Any]:
        if v is None:
            return {}
        if isinstance(v, ArtifactGenerationConfig):
            return v.model_dump()
        if not isinstance(v, dict):
            raise ValueError("'config' must be a dictionary.")
        validated = ArtifactGenerationConfig.model_validate(v)
        return validated.model_dump()

class ArtifactJobRead(BaseModel):
    id: str
    upload_id: str
    knowledge_version_id: str
    artifact_type: ArtifactType
    status: ArtifactStatus
    config: Dict[str, Any]
    plan: Optional[Dict[str, Any]] = None
    artifact_uri: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True
