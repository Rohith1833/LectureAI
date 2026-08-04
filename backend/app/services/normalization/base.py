import uuid
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field

from app.schemas.document import DocumentExtractionResult


class TransformationRecord(BaseModel):
    """Traceable ledger entry documenting a single block level text or layout change."""

    transformation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    step_name: str
    target_block_id: str
    action: str  # "modified", "deleted", "merged", "inserted"
    original_hash: Optional[str] = None
    transformed_hash: Optional[str] = None
    reason: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Verbose/Debug mode fields (empty by default to minimize DB memory footprint)
    original_text: Optional[str] = None
    transformed_text: Optional[str] = None

    @classmethod
    def create_record(
        cls,
        step_name: str,
        target_block_id: str,
        action: str,
        reason: str,
        original_text: Optional[str] = None,
        transformed_text: Optional[str] = None,
        verbose: bool = False,
    ) -> "TransformationRecord":
        """Factory method to calculate hashes and selectively populate full text based on verbose setting."""
        orig_hash = (
            hashlib.sha256(original_text.encode("utf-8")).hexdigest()
            if original_text
            else None
        )
        trans_hash = (
            hashlib.sha256(transformed_text.encode("utf-8")).hexdigest()
            if transformed_text
            else None
        )

        return cls(
            step_name=step_name,
            target_block_id=target_block_id,
            action=action,
            original_hash=orig_hash,
            transformed_hash=trans_hash,
            reason=reason,
            original_text=original_text if verbose else None,
            transformed_text=transformed_text if verbose else None,
        )


class StageMetrics(BaseModel):
    """Detailed performance and operation count metrics for a single normalizer stage."""

    execution_time_ms: float
    modified_blocks_count: int = 0
    inserted_blocks_count: int = 0
    removed_blocks_count: int = 0
    merged_blocks_count: int = 0
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class StageResult(BaseModel):
    """Structured response returned by a single BaseNormalizer implementation execution."""

    document: DocumentExtractionResult
    transformations: List[TransformationRecord]
    metrics: StageMetrics


class ImmutableMetadata(BaseModel):
    """Read-only document execution metadata block to prevent side effects between stages."""

    upload_id: str
    document_id: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)


class NormalizationContext:
    """Execution context containing immutable configs and isolated mutable history logs."""

    def __init__(self, metadata: ImmutableMetadata, debug_mode: bool = False):
        self.metadata = metadata  # Read-only execution metadata parameters
        self.debug_mode = debug_mode
        self._transformations: List[TransformationRecord] = []
        self._snapshots: List[Tuple[str, Dict[str, Any]]] = []  # List of (version_name, serialized_snapshot)

    def add_transformations(self, records: List[TransformationRecord]) -> None:
        """Append transformation ledger entries to history log."""
        self._transformations.extend(records)

    def get_transformations(self) -> List[TransformationRecord]:
        """Retrieve overall transformation records logs."""
        return self._transformations

    def take_snapshot(self, version_name: str, document: DocumentExtractionResult) -> None:
        """Store a logical version snapshot of the document at this pipeline stage."""
        # Serialize model to clean dict representation
        self._snapshots.append((version_name, document.model_dump()))

    def get_snapshot(self, version_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific document version snapshot by its logical stage name."""
        for name, snap in self._snapshots:
            if name == version_name:
                return snap
        return None

    def get_snapshots_history(self) -> List[Tuple[str, Dict[str, Any]]]:
        """Retrieve the sequence history of logical version snapshots taken."""
        return self._snapshots


class BaseNormalizer(ABC):
    """Abstract interface defining contracts for modular document layout cleaning normalizers."""

    @abstractmethod
    def get_name(self) -> str:
        """Return the unique uppercase logical name of this Normalization step."""
        pass

    @abstractmethod
    def run(
        self, doc: DocumentExtractionResult, context: NormalizationContext
    ) -> StageResult:
        """Execute layout normalization over document blocks.

        Returns a structured StageResult containing the modified document, transformation records, and metrics.
        """
        pass


class PipelineLifecycleHook:
    """Pluggable callback observer interface for pipeline execution monitoring and metrics logging."""

    def before_pipeline(
        self, pipeline: Any, doc: DocumentExtractionResult, context: NormalizationContext
    ) -> None:
        pass

    def before_stage(
        self,
        pipeline: Any,
        stage_name: str,
        doc: DocumentExtractionResult,
        context: NormalizationContext,
    ) -> None:
        pass

    def after_stage(
        self,
        pipeline: Any,
        stage_name: str,
        doc: DocumentExtractionResult,
        context: NormalizationContext,
        stage_result: StageResult,
    ) -> None:
        pass

    def pipeline_complete(
        self,
        pipeline: Any,
        doc: DocumentExtractionResult,
        context: NormalizationContext,
        report: "NormalizationReport",
    ) -> None:
        pass


class NormalizationReport(BaseModel):
    """Overall consolidated statistics and history reports of the normalization run."""

    steps_executed: List[str]
    total_transformations: int
    total_execution_time_ms: float
    stage_metrics: Dict[str, StageMetrics]  # Keyed by normalizer step name
    transformations: List[TransformationRecord]
