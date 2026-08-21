from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from app.schemas.academic import AcademicNodeCategory


class KnowledgeRelationshipType(str, Enum):
    CONTAINS = "CONTAINS"
    PREREQUISITE_OF = "PREREQUISITE_OF"
    EXPLAINS = "EXPLAINS"
    PROVES = "PROVES"
    ILLUSTRATES = "ILLUSTRATES"


class KnowledgeEvidenceProvenance(str, Enum):
    EXPLICIT_CLASSIFIER = "EXPLICIT_CLASSIFIER"
    HUMAN_OVERRIDE = "HUMAN_OVERRIDE"
    DERIVED_HIERARCHY = "DERIVED_HIERARCHY"
    UNKNOWN = "UNKNOWN"


class KnowledgeEvidenceSchema(BaseModel):
    id: Optional[str] = None
    entity_id: str
    document_id: str
    page_number: Optional[int] = Field(None, gt=0, description="1-indexed page number")
    section_title: Optional[str] = None
    source_node_id: Optional[str] = None
    source_anchor_key: Optional[str] = None
    text_reference: Optional[str] = None
    provenance: KnowledgeEvidenceProvenance
    
    # Layout Coordinates
    x0: Optional[float] = None
    y0: Optional[float] = None
    x1: Optional[float] = None
    y1: Optional[float] = None

    metadata: Optional[Dict[str, Any]] = None

    model_config = {
        "populate_by_name": True,
        "from_attributes": True
    }

    @model_validator(mode="before")
    @classmethod
    def map_metadata_before(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "metadata_json" in data:
                data["metadata"] = data.get("metadata_json")
        else:
            if hasattr(data, "metadata_json"):
                try:
                    data.metadata = data.metadata_json
                except AttributeError:
                    pass
        return data

    @model_validator(mode="after")
    def validate_provenance_and_coordinates(self) -> "KnowledgeEvidenceSchema":
        coords = [self.x0, self.y0, self.x1, self.y1]
        has_some = any(c is not None for c in coords)
        has_all = all(c is not None for c in coords)
        if has_some and not has_all:
            raise ValueError("All coordinate fields (x0, y0, x1, y1) must be populated together or remain null.")
        return self


class KnowledgeEntitySchema(BaseModel):
    id: Optional[str] = None
    knowledge_version_id: str
    entity_type: AcademicNodeCategory
    title: str = Field(..., min_length=1, max_length=256)
    content: str = Field(..., description="Semantic text content representing this knowledge entity")
    stable_id: str = Field(..., min_length=1, description="Stable cross-version semantic identifier")
    metadata: Optional[Dict[str, Any]] = None
    evidence: List[KnowledgeEvidenceSchema] = Field(default_factory=list)

    model_config = {
        "populate_by_name": True,
        "from_attributes": True
    }

    @model_validator(mode="before")
    @classmethod
    def map_metadata_before(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "metadata_json" in data:
                data["metadata"] = data.get("metadata_json")
        else:
            if hasattr(data, "metadata_json"):
                try:
                    data.metadata = data.metadata_json
                except AttributeError:
                    pass
        return data


class KnowledgeRelationshipSchema(BaseModel):
    id: Optional[str] = None
    knowledge_version_id: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: KnowledgeRelationshipType
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    is_inferred: bool = False
    is_human_confirmed: bool = False
    metadata: Optional[Dict[str, Any]] = None

    model_config = {
        "populate_by_name": True,
        "from_attributes": True
    }

    @model_validator(mode="before")
    @classmethod
    def map_metadata_before(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "metadata_json" in data:
                data["metadata"] = data.get("metadata_json")
        else:
            if hasattr(data, "metadata_json"):
                try:
                    data.metadata = data.metadata_json
                except AttributeError:
                    pass
        return data

    @model_validator(mode="after")
    def validate_no_self_loops(self) -> "KnowledgeRelationshipSchema":
        if self.source_entity_id == self.target_entity_id:
            raise ValueError("Self-referencing relationships are strictly prohibited.")
        return self


class KnowledgeVersionStatus(str, Enum):
    BUILDING = "BUILDING"
    FINALIZED = "FINALIZED"


class KnowledgeVersionSchema(BaseModel):
    id: Optional[str] = None
    upload_id: str
    snapshot_id: str
    schema_version: str = "1.0.0"
    created_at: Optional[float] = None
    status: KnowledgeVersionStatus = KnowledgeVersionStatus.BUILDING
    metadata: Optional[Dict[str, Any]] = None
    entities: List[KnowledgeEntitySchema] = Field(default_factory=list)
    relationships: List[KnowledgeRelationshipSchema] = Field(default_factory=list)

    model_config = {
        "populate_by_name": True,
        "from_attributes": True
    }

    @model_validator(mode="before")
    @classmethod
    def map_metadata_before(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "metadata_json" in data:
                data["metadata"] = data.get("metadata_json")
        else:
            if hasattr(data, "metadata_json"):
                try:
                    data.metadata = data.metadata_json
                except AttributeError:
                    pass
        return data
