from typing import Optional
from app.services.generation.base import LLMGenerationRequest, LLMGenerationResponse
from app.services.generation.errors import LLMProviderError


class MockLLMProvider:
  """Deterministic mock provider simulating vendor API behaviors in unit tests."""

  def __init__(
      self,
      scenario: str = "success",
      error_message: str = "Simulated API failure",
      custom_response: Optional[str] = None
  ):
    self.scenario = scenario.lower()
    self.error_message = error_message
    self.custom_response = custom_response

  async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
    """Simulates asynchronous structured text generation based on the configured scenario."""
    if self.scenario == "provider_failure":
      raise LLMProviderError(self.error_message)

    if self.scenario == "malformed_output":
      return LLMGenerationResponse(
          raw_response=self.custom_response or "invalid-raw-text-{malformed-json",
          structured_output=None,
          token_usage={"prompt_tokens": 15, "completion_tokens": 5},
          model_name="mock-malformed-model"
      )

    if self.scenario == "invalid_citation":
      structured_data = {
          "answer": "This is an answer referencing an invalid citation ID.",
          "claims": [
              {
                  "claim_id": "c_mock_1",
                  "text": "This assertion is backed by an unknown citation.",
                  "citation_ids": ["S99"],
                  "grounding_status": "UNSUPPORTED"
              }
          ]
      }
      return LLMGenerationResponse(
          raw_response="Answer text referencing invalid citation [S99].",
          structured_output=structured_data,
          token_usage={"prompt_tokens": 20, "completion_tokens": 10},
          model_name="mock-invalid-citation-model"
      )

    # Default 'success' scenario
    structured_data = {
        "answer": "This is a deterministic correct grounded answer.",
        "claims": [
            {
                "claim_id": "c_mock_1",
                "text": "This is a statement.",
                "citation_ids": ["S1"],
                "grounding_status": "SUPPORTED"
            }
        ]
    }
    return LLMGenerationResponse(
        raw_response=self.custom_response or "This is a deterministic correct grounded answer [S1].",
        structured_output=structured_data,
        token_usage={"prompt_tokens": 30, "completion_tokens": 15},
        model_name="mock-success-model"
    )
