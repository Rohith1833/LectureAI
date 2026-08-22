class GenerationError(Exception):
  """Base exception for all AI generation layer errors."""
  pass


class LLMProviderError(GenerationError):
  """Raised when an external LLM provider API call fails or returns errors."""
  pass


class GroundingValidationError(GenerationError):
  """Raised when model outputs fail structural parsing or citation validity checks."""
  pass
