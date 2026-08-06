from abc import ABC, abstractmethod
import time
from typing import List, Optional
from pydantic import BaseModel, Field


class PipelineEvent(BaseModel):
    timestamp: float = Field(default_factory=time.time)
    upload_id: str


class PipelineStarted(PipelineEvent):
    execution_order: List[str]


class ModuleStarted(PipelineEvent):
    module_name: str


class ModuleFinished(PipelineEvent):
    module_name: str
    execution_time_ms: float
    annotations_generated: int


class ModuleSkipped(PipelineEvent):
    module_name: str
    reason: str


class ModuleFailed(PipelineEvent):
    module_name: str
    error_message: str
    fatal: bool


class PipelineFinished(PipelineEvent):
    total_time_ms: float
    success: bool
    annotations_count: int


class HierarchyConstructionStarted(PipelineEvent):
    pass


class HierarchyNodeCreated(PipelineEvent):
    block_id: str
    parent_id: Optional[str]
    relation: str


class HierarchyCompleted(PipelineEvent):
    node_count: int


class ValidationStarted(PipelineEvent):
    pass


class ValidationWarning(PipelineEvent):
    warning_type: str
    block_id: str


class ValidationCompleted(PipelineEvent):
    consistency_score: Optional[float] = None
    warning_count: Optional[int] = None


class QualityAnalysisStarted(PipelineEvent):
    pass


class OCRQualityEvaluated(PipelineEvent):
    ocr_score: float


class StructuralQualityEvaluated(PipelineEvent):
    structural_score: float


class SemanticQualityEvaluated(PipelineEvent):
    semantic_score: float


class DocumentQualityCompleted(PipelineEvent):
    overall_score: float
    warning_count: int


class PipelineEventListener(ABC):
    """Observer interface for subscribers listening to progress metrics."""

    @abstractmethod
    def on_event(self, event: PipelineEvent) -> None:
        pass


class PipelineEventPublisher:
    """Orchestrates delivery of pipeline milestones to registered event listeners."""

    def __init__(self):
        self._listeners: List[PipelineEventListener] = []

    def subscribe(self, listener: PipelineEventListener) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unsubscribe(self, listener: PipelineEventListener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def publish(self, event: PipelineEvent) -> None:
        for listener in self._listeners:
            try:
                listener.on_event(event)
            except Exception:
                # Suppress errors from listeners to avoid disrupting engine runs
                pass
