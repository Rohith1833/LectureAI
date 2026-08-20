from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ModuleMetrics(BaseModel):
    module_name: str
    execution_time_ms: float
    success: bool
    annotations_generated: int
    error_message: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    skipped: bool = False


class IntelligenceReport(BaseModel):
    upload_id: str
    execution_order: List[str]
    metrics: Dict[str, ModuleMetrics]
    total_time_ms: float
    overall_confidence_average: float
    success: bool = True

    # Hierarchy and Graph Telemetry
    hierarchy_depth: Optional[int] = None
    total_sections: Optional[int] = None
    orphan_count: Optional[int] = None
    graph_statistics: Optional[Dict[str, Any]] = None
    root_count: Optional[int] = None
    hierarchy_consistency_score: Optional[float] = None

    # Quality & Reliability Metrics
    ocr_quality_score: Optional[float] = None
    layout_quality_score: Optional[float] = None
    semantic_quality_score: Optional[float] = None
    hierarchy_quality_score: Optional[float] = None
    reading_quality_score: Optional[float] = None
    overall_quality_score: Optional[float] = None
    quality_warnings: List[dict] = Field(default_factory=list)
    processing_recommendations: List[dict] = Field(default_factory=list)

    # Academic Quality Metrics
    academic_quality_score: Optional[float] = None
    academic_coverage_score: Optional[float] = None
    academic_density_score: Optional[float] = None
    academic_orphan_count: Optional[int] = None
    academic_warnings: List[dict] = Field(default_factory=list)
    academic_recommendations: List[dict] = Field(default_factory=list)
