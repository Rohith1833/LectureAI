from typing import Any, Dict, Optional, Protocol
from pydantic import BaseModel, Field


class LLMGenerationRequest(BaseModel):
  """Provider-neutral model representing a structured generation request."""
  prompt: str = Field(..., description="Constructed prompt query text.")
  system_instruction: Optional[str] = Field(None, description="Global system guidance or context constraints.")
  temperature: float = Field(0.0, description="Sampling temperature to enforce determinism.")
  json_schema: Optional[Dict[str, Any]] = Field(None, description="Optional target schema template for structured JSON responses.")


class LLMGenerationResponse(BaseModel):
  """Provider-neutral model capturing the raw response payload and token usage."""
  raw_response: str = Field(..., description="Verbatim text response from the model.")
  structured_output: Optional[Dict[str, Any]] = Field(None, description="Parsed structured JSON representation.")
  token_usage: Optional[Dict[str, int]] = Field(None, description="Model token usage counts (prompt, output).")
  model_name: str = Field("mock-model", description="Identifier of the model used.")


class LLMProvider(Protocol):
  """Interface definition to isolate external LLM vendor clients."""

  async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
    """Executes structured AI text generation asynchronously."""
    ...
