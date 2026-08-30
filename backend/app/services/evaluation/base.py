from abc import ABC, abstractmethod
from typing import List
from app.schemas.evaluation import EvaluationRequest, MetricScore


class BaseEvaluator(ABC):
    """
    Abstract base interface for modular generation evaluators.
    Evaluators analyze an EvaluationRequest and return one or more MetricScore instances.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique descriptive name identifying the evaluator."""
        pass

    @abstractmethod
    async def evaluate(self, request: EvaluationRequest) -> List[MetricScore]:
        """
        Executes quality and grounding assessment against the provided request.

        Args:
            request: EvaluationRequest containing generation input, output, and context.

        Returns:
            List of MetricScore instances quantifying quality dimensions.
        """
        pass
