from abc import ABC, abstractmethod
from typing import Dict, Any
from app.services.intelligence.context import IntelligenceContext


class BaseQualityEvaluator(ABC):
    """Abstract interface for pluggable document quality checkers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the evaluator for reporting and telemetry."""
        pass

    @abstractmethod
    def evaluate(self, context: IntelligenceContext) -> Dict[str, Any]:
        """Runs validation checks and returns scores, warnings, and recommendations."""
        pass
