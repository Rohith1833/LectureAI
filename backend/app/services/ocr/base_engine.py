from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseOCREngine(ABC):
    """Abstract base class defining interface contracts for pluggable OCR engines."""

    @abstractmethod
    def get_name(self) -> str:
        """Return the lowercase identifier name of the OCR Engine."""
        pass

    @abstractmethod
    def get_version(self) -> str:
        """Return the current version string of the engine CLI or dynamic library."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the engine's external dependencies are installed and runnable."""
        pass

    @abstractmethod
    def perform_ocr(self, image_path: str) -> List[Dict[str, Any]]:
        """Run OCR on a preprocessed local page image file.

        Returns a list of word layout dict elements containing:
        - "text": str
        - "bbox": Tuple[float, float, float, float] (x0, y0, x1, y1 relative to image pixels)
        - "confidence": float (0.0 to 1.0)
        - "words": List[Dict[str, Any]] (optional breakdown, each word with "text", "bbox", "confidence")
        """
        pass
