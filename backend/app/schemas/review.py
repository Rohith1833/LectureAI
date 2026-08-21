from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class NodeReviewState(str, Enum):
    UNREVIEWED = "UNREVIEWED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    MODIFIED = "MODIFIED"


class DocumentReviewState(str, Enum):
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"


class PipelineRunReference(BaseModel):
    """Holds references to a specific pipeline execution run."""
    pipeline_run_id: str
    timestamp: float = Field(..., description="Timestamp of the pipeline run")


class AcademicGraphVersion(BaseModel):
    """Domain model representing graph fingerprints, versions, and approval metadata."""
    upload_id: str
    pipeline_run_id: str
    base_graph_fingerprint: str
    resolved_graph_fingerprint: str
    approval_version: Optional[str] = None
    approval_timestamp: Optional[float] = None
    reviewer_id: Optional[str] = None


from typing import List


class ReconciliationStatus(str, Enum):
    CLEAN = "CLEAN"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    STALE_OVERRIDES = "STALE_OVERRIDES"
    CONFLICTS = "CONFLICTS"
    INVALID_GRAPH = "INVALID_GRAPH"


class ResolvedGraphResult(BaseModel):
    nodes: List["AcademicNode"] = Field(default_factory=list)
    edges: List["AcademicEdge"] = Field(default_factory=list)
    base_graph_fingerprint: str
    resolved_graph_fingerprint: str
    applied_override_ids: List[str] = Field(default_factory=list)
    stale_override_ids: List[str] = Field(default_factory=list)
    conflicted_override_ids: List[str] = Field(default_factory=list)
    validation_errors: List[str] = Field(default_factory=list)
    validation_warnings: List[str] = Field(default_factory=list)
    reconciliation_status: ReconciliationStatus


class ApprovalCheck(BaseModel):
    code: str
    passed: bool
    severity: str  # "BLOCKER" or "WARNING" or "INFO"
    message: str


class ApprovalReadiness(BaseModel):
    eligible: bool
    checks: List[ApprovalCheck]
    blocking_reasons: List[str]
    warnings: List[str]
    current_revision: int
    resolved_graph_fingerprint: str




