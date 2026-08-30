from app.schemas.generation import GenerationMode
from app.services.generation.modes.base import GenerationModeStrategy
from app.services.generation.modes.qa import QAModeStrategy
from app.services.generation.modes.explanation import ExplanationStrategy
from app.services.generation.modes.summary import SummaryStrategy
from app.services.generation.modes.comparison import ComparisonStrategy
from app.services.generation.modes.study_guide import StudyGuideStrategy


class StrategyRegistry:
    """
    Registry that resolves a GenerationMode to its active implementation strategy.
    """

    def __init__(self) -> None:
        self._registry = {
            GenerationMode.QA: QAModeStrategy(),
            GenerationMode.EXPLANATION: ExplanationStrategy(),
            GenerationMode.SUMMARY: SummaryStrategy(),
            GenerationMode.COMPARISON: ComparisonStrategy(),
            GenerationMode.STUDY_GUIDE: StudyGuideStrategy(),
        }

    def get(self, mode: GenerationMode) -> GenerationModeStrategy:
        """
        Resolve a GenerationMode to its strategy.

        Raises:
            ValueError: if the mode is unknown or not supported.
        """
        if mode not in self._registry:
            raise ValueError(f"Generation mode '{mode}' is not currently supported or implemented.")
        return self._registry[mode]


# Global singleton strategy registry
strategy_registry = StrategyRegistry()
