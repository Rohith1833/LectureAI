import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.schemas.document import BlockType


class ConfidenceScore(BaseModel):
    """Encapsulates a normalized confidence score and its contributing metrics."""
    score: float = Field(..., ge=0.0, le=1.0)
    contributors: Dict[str, float] = Field(default_factory=dict)
    method: str = "heuristic"


class BaseAnnotation(BaseModel):
    """Root base class for all metadata annotations generated within the framework."""
    annotation_id: str
    target_id: str  # References a block_id, page_number, or table_id
    provenance: str  # The module name that generated this annotation
    confidence: ConfidenceScore
    timestamp: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    version: str = "1.0.0"


class SemanticAnnotation(BaseAnnotation):
    """Annotations related to semantic structures (e.g. classification, headers)."""
    assigned_type: BlockType
    reasoning: List[str] = Field(default_factory=list)


class HierarchyAnnotation(BaseAnnotation):
    """Defines relationship linkages between layout blocks (e.g. parent-child, next-previous)."""
    parent_id: Optional[str] = None
    child_ids: List[str] = Field(default_factory=list)
    relation_type: str  # e.g., "section_to_paragraph", "list_to_item"


class ReadingOrderAnnotation(BaseAnnotation):
    """Establishes reading sequence direction and flow index order."""
    sequence_index: int
    column_index: int = 0
    reading_direction: str = "LTR"  # Left-to-Right


class QualityAnnotation(BaseAnnotation):
    """OCR quality metrics, structural readability, and validation flags."""
    contrast_ratio: Optional[float] = None
    blurriness_score: Optional[float] = None
    is_scanned: bool = False
    ocr_confidence_raw: Optional[float] = None

    # Extended Quality Telemetry
    ocr_quality_score: Optional[float] = None
    layout_quality_score: Optional[float] = None
    semantic_quality_score: Optional[float] = None
    hierarchy_quality_score: Optional[float] = None
    reading_quality_score: Optional[float] = None
    overall_quality_score: Optional[float] = None


class LayoutAnnotation(BaseAnnotation):
    """Visual bounds, coordinates adjustment, and segment coordinates."""
    x0: float
    y0: float
    x1: float
    y1: float
    columns_detected: int = 1


class AcademicAnnotation(BaseAnnotation):
    """Represents an identified academic structure in the document."""
    academic_type: str            # e.g., "DEFINITION", "THEOREM", "LEARNING_OBJECTIVE"
    concept_labels: List[str] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""
