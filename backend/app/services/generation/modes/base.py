from typing import Any, Dict, Protocol, runtime_checkable
from app.schemas.generation import GenerationMode


@runtime_checkable
class GenerationModeStrategy(Protocol):
    """
    Defines the contract for mode-specific behavior in the generation pipeline.

    A strategy handles:
    - Mode identity
    - System instructions
    - Grounding rules/instructions
    - Output format instructions
    - Structured JSON output schema for model-side enforcement (Groq API)
    """

    @property
    def mode(self) -> GenerationMode:
        """The GenerationMode enum associated with this strategy."""
        ...

    @property
    def system_instruction(self) -> str:
        """The high-level identity system prompt instructions."""
        ...

    @property
    def grounding_instructions(self) -> str:
        """The strict grounding rules/constraints."""
        ...

    @property
    def output_requirements(self) -> str:
        """Textual description of the required output structure."""
        ...

    @property
    def json_schema(self) -> Dict[str, Any]:
        """The standard JSON Schema describing the target LLM response structure."""
        ...
