from abc import ABC, abstractmethod
from typing import Any, Dict, List
from pydantic import BaseModel, Field
from app.services.intelligence.context import IntelligenceContext


class ModuleMetadata(BaseModel):
    """Immutable version and identity metrics for plugin modules."""
    name: str
    version: str
    author: str
    stage: str  # e.g., "layout", "hierarchy", "normalization"
    priority: int = 100
    experimental: bool = False
    enabled: bool = True
    dependencies: List[str] = Field(default_factory=list)


class BaseIntelligenceModule(ABC):
    """Abstract interface defining execution contracts for all intelligence modules."""

    @property
    @abstractmethod
    def metadata(self) -> ModuleMetadata:
        """Returns version, dependencies, and author metadata for this module."""
        pass

    def supported_document_types(self) -> List[str]:
        """Returns list of supported doc classes, e.g., ['scanned_pdf', 'native_pdf']."""
        return ["*"]

    def initialize(self, config: dict) -> None:
        """Invoked when pipeline starts, for setting up weights and hyperparameters."""
        pass

    @abstractmethod
    def execute(self, context: IntelligenceContext) -> None:
        """Executes the analysis algorithm, updating the context annotation registry."""
        pass

    def validate(self, context: IntelligenceContext) -> bool:
        """Performs structural assertions on outputs before completing execution."""
        return True

    def cleanup(self) -> None:
        """Releases heavy references or temporary files."""
        pass


# AI Compatibility Layer (Unused for now, but ready for future extensions)

class InferenceRequest(BaseModel):
    """Encapsulates input prompt, model version, and completion limits."""
    model_name: str
    prompt: str
    temperature: float = 0.0
    max_tokens: int = 256
    extra_params: Dict[str, Any] = Field(default_factory=dict)


class InferenceResult(BaseModel):
    """Encapsulates raw string completion, confidence scores, and token usage."""
    raw_response: str
    token_usage: Dict[str, int]
    model_version: str
    confidence: float


class InferenceContext(ABC):
    """Abstract interface defining the execution hook for executing model evaluations."""
    @abstractmethod
    def execute_inference(self, request: InferenceRequest) -> InferenceResult:
        pass
