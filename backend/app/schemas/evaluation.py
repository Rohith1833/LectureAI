from enum import Enum
from typing import Any, Dict, List, Optional
import time
import uuid
from pydantic import BaseModel, Field, field_validator
from app.schemas.generation import GenerationMode, GenerationRequest, GenerationResult


class EvaluationVerdict(str, Enum):
    """Categorical verdict assessing overall generation quality."""
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class MetricScore(BaseModel):
    """Represents the evaluation score and diagnostics for a single metric."""
    name: str = Field(..., description="Unique metric identifier, e.g. citation_validity_rate")
    score: float = Field(..., description="Normalized score bounded between 0.0 and 1.0")
    threshold: float = Field(..., description="Minimum score required to pass this metric")
    passed: bool = Field(..., description="Whether score meets or exceeds the threshold")
    weight: float = Field(default=1.0, description="Relative weighting factor for composite score")
    reason: Optional[str] = Field(default=None, description="Diagnostic explanation or failure cause")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Supplementary metric telemetry")

    @field_validator("score", "threshold")
    @classmethod
    def validate_bounds(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"Metric value must be bounded between 0.0 and 1.0, got {v}")
        return v

    @field_validator("weight")
    @classmethod
    def validate_weight(cls, v: float) -> float:
        if v < 0.0:
            raise ValueError(f"Metric weight cannot be negative, got {v}")
        return v


class EvaluationRequest(BaseModel):
    """Input envelope delivered to the evaluation engine for quality assessment."""
    generation_request: GenerationRequest = Field(..., description="Original user prompt and scope options")
    generation_result: GenerationResult = Field(..., description="Output produced by the generation pipeline")
    context_sources: Dict[str, Any] = Field(
        default_factory=dict,
        description="Retrieved canonical context sources supplied during prompt construction",
    )
    evaluation_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Custom evaluation parameters, weights, and thresholds",
    )


class EvaluationResult(BaseModel):
    """Final assessment summary produced by the evaluation engine."""
    evaluation_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique evaluation run ID")
    mode: GenerationMode = Field(..., description="Generation mode under evaluation")
    overall_passed: bool = Field(..., description="True if all critical metric thresholds are satisfied")
    overall_score: float = Field(..., description="Weighted composite quality score between 0.0 and 1.0")
    verdict: EvaluationVerdict = Field(..., description="Overall evaluation verdict (PASS, WARNING, FAIL)")
    metrics: List[MetricScore] = Field(default_factory=list, description="Detailed list of individual metric scores")
    diagnostics: Dict[str, Any] = Field(default_factory=dict, description="Summary diagnostics and execution metadata")
    evaluated_at: float = Field(default_factory=time.time, description="Unix timestamp of evaluation execution")
