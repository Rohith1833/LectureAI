from typing import Any, Callable, Dict, List, Optional, Type, TypeVar
from app.services.intelligence.annotations import BaseAnnotation

T = TypeVar("T", bound=BaseAnnotation)


class AnnotationStore:
    """Provides querying, statistics, and persistence operations for document annotations."""

    def __init__(self):
        self._annotations: Dict[str, BaseAnnotation] = {}

    def add(self, annotation: BaseAnnotation) -> None:
        self._annotations[annotation.annotation_id] = annotation

    def remove(self, annotation_id: str) -> Optional[BaseAnnotation]:
        return self._annotations.pop(annotation_id, None)

    def update(self, annotation: BaseAnnotation) -> None:
        if annotation.annotation_id in self._annotations:
            self._annotations[annotation.annotation_id] = annotation

    def find(self, annotation_id: str) -> Optional[BaseAnnotation]:
        return self._annotations.get(annotation_id)

    def find_by_type(self, annotation_class: Type[T]) -> List[T]:
        return [anno for anno in self._annotations.values() if isinstance(anno, annotation_class)]  # type: ignore

    def find_by_target(self, target_id: str) -> List[BaseAnnotation]:
        return [anno for anno in self._annotations.values() if anno.target_id == target_id]

    def query(self, filter_fn: Callable[[BaseAnnotation], bool]) -> List[BaseAnnotation]:
        return [anno for anno in self._annotations.values() if filter_fn(anno)]

    def statistics(self) -> Dict[str, Any]:
        """Returns statistics on the numbers and categories of annotations present."""
        counts: Dict[str, int] = {}
        for anno in self._annotations.values():
            name = anno.__class__.__name__
            counts[name] = counts.get(name, 0) + 1
        return {"total_count": len(self._annotations), "type_counts": counts}


from app.services.intelligence.events import PipelineEventPublisher

class IntelligenceContext:
    """State-isolated execution context passed between processing modules."""

    def __init__(
        self,
        document: Any,
        page_metadata: Dict[int, Any],
        document_metadata: Any,
        settings: Any
    ):
        self.document = document
        self.page_metadata = page_metadata
        self.document_metadata = document_metadata
        self.settings = settings
        self.annotation_store = AnnotationStore()
        self.event_publisher = PipelineEventPublisher()
        self.shared_cache: Dict[str, Any] = {}
        self.diagnostics: List[dict] = []

    def cache_set(self, key: str, value: Any) -> None:
        self.shared_cache[key] = value

    def cache_get(self, key: str) -> Optional[Any]:
        return self.shared_cache.get(key)
