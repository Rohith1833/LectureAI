from app.schemas.evaluation import (
    EvaluationVerdict,
    MetricScore,
    EvaluationRequest,
    EvaluationResult,
)
from app.services.evaluation.base import BaseEvaluator
from app.services.evaluation.engine import EvaluationEngine
from app.services.evaluation.evaluators.structural import StructuralEvaluator
from app.services.evaluation.evaluators.citation import CitationEvaluator
from app.services.evaluation.evaluators.abstention import AbstentionEvaluator
from app.services.evaluation.evaluators.faithfulness import FaithfulnessEvaluator
from app.services.evaluation.evaluators.relevance import RelevanceEvaluator
from app.services.evaluation.evaluators.comparison import ComparisonEvaluator
from app.services.evaluation.evaluators.study_guide import StudyGuideEvaluator
from app.services.evaluation.benchmark import (
    EvaluationCase,
    BenchmarkReport,
    BenchmarkRunner,
)
from app.services.evaluation.quality_gate import (
    EvaluationGateConfig,
    EvaluationGateResult,
    EvaluationQualityGate,
)
from app.services.evaluation.run_benchmark import run_benchmark_cli


def create_default_evaluation_engine() -> EvaluationEngine:
    """Instantiates an EvaluationEngine pre-registered with all core and mode-specific evaluators."""
    return EvaluationEngine([
        StructuralEvaluator(),
        CitationEvaluator(),
        AbstentionEvaluator(),
        FaithfulnessEvaluator(),
        RelevanceEvaluator(),
        ComparisonEvaluator(),
        StudyGuideEvaluator(),
    ])


__all__ = [
    "EvaluationVerdict",
    "MetricScore",
    "EvaluationRequest",
    "EvaluationResult",
    "BaseEvaluator",
    "EvaluationEngine",
    "StructuralEvaluator",
    "CitationEvaluator",
    "AbstentionEvaluator",
    "FaithfulnessEvaluator",
    "RelevanceEvaluator",
    "ComparisonEvaluator",
    "StudyGuideEvaluator",
    "EvaluationCase",
    "BenchmarkReport",
    "BenchmarkRunner",
    "EvaluationGateConfig",
    "EvaluationGateResult",
    "EvaluationQualityGate",
    "run_benchmark_cli",
    "create_default_evaluation_engine",
]
