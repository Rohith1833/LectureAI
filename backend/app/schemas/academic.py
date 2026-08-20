from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AcademicNodeCategory(str, Enum):
    UNIT = "UNIT"
    CHAPTER = "CHAPTER"
    SECTION = "SECTION"
    TOPIC = "TOPIC"
    CONCEPT = "CONCEPT"
    DEFINITION = "DEFINITION"
    THEOREM = "THEOREM"
    PROOF = "PROOF"
    FORMULA = "FORMULA"
    ALGORITHM = "ALGORITHM"
    EXAMPLE = "EXAMPLE"
    EXERCISE = "EXERCISE"
    LEARNING_OBJECTIVE = "LEARNING_OBJECTIVE"
    SUMMARY = "SUMMARY"
    REVIEW_QUESTION = "REVIEW_QUESTION"
    REFERENCE = "REFERENCE"
    DIAGRAM = "DIAGRAM"
    APPENDIX = "APPENDIX"


class AcademicNode(BaseModel):
    """Represents a node in the logical academic hierarchy and concept graph."""
    node_id: str
    category: AcademicNodeCategory
    title: str
    target_block_id: Optional[str] = None  # Reference to DocumentGraph BlockSchema block_id
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AcademicEdge(BaseModel):
    """Represents a pedagogical, prerequisite, or compositional relationship between nodes."""
    source_node_id: str
    target_node_id: str
    edge_type: str  # e.g., "CONTAINS", "PREREQUISITE_OF", "EXPLAINS", "PROVES", "ILLUSTRATES"
    confidence: float = Field(1.0, ge=0.0, le=1.0)
