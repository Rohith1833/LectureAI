import asyncio
from typing import Any, Dict, Optional
import groq
from groq import AsyncGroq

from app.core.config import settings
from app.services.generation.base import LLMGenerationRequest, LLMGenerationResponse
from app.services.generation.errors import (
  LLMProviderError,
  GroundingValidationError,
)


class GroqProvider:
  """Infrastructure adapter implementing the LLMProvider protocol for the Groq API."""

  def __init__(
      self,
      api_key: Optional[str] = None,
      model: Optional[str] = None,
      timeout: float = 30.0
  ):
    self.api_key = api_key or settings.GROQ_API_KEY
    self.model = model or settings.GROQ_MODEL
    self.timeout = timeout

    if not self.api_key:
      raise LLMProviderError("Missing API key: GROQ_API_KEY environment variable is not set.")

    # Initialize AsyncGroq client with max_retries=0 so SDK internal retries do not multiply with our bounded loop
    self.client = AsyncGroq(api_key=self.api_key, timeout=self.timeout, max_retries=0)

  async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
    """Translates LLMGenerationRequest into Groq chat completion and returns LLMGenerationResponse."""
    messages = []
    if request.system_instruction:
      messages.append({"role": "system", "content": request.system_instruction})
    messages.append({"role": "user", "content": request.prompt})

    response_format = None
    if request.json_schema:
      response_format = {
          "type": "json_schema",
          "json_schema": {
              "name": "structured_generation",
              "schema": request.json_schema
          }
      }

    max_retries = 2  # Total 3 attempts (attempt 0, 1, 2)
    for attempt in range(max_retries + 1):
      try:
        chat_completion = await self.client.chat.completions.create(
            messages=messages,
            model=self.model,
            temperature=request.temperature,
            response_format=response_format
        )
        break
      except groq.AuthenticationError:
        # Non-retryable authentication failure; avoid exposing credentials
        raise LLMProviderError("Authentication failure with LLM provider. Verify GROQ_API_KEY configuration.")
      except groq.BadRequestError as e:
        # Non-retryable schema or bad request
        raise LLMProviderError(f"Invalid request or model rejected by LLM provider: {str(e)}")
      except groq.RateLimitError as e:
        if attempt == max_retries:
          raise LLMProviderError(f"Rate limit exceeded on LLM provider after {max_retries + 1} attempts.")
        retry_after = 1.0 * (attempt + 1)
        if hasattr(e, "response") and e.response is not None:
          header_val = e.response.headers.get("retry-after")
          if header_val:
            try:
              retry_after = min(float(header_val), 10.0)
            except ValueError:
              pass
        await asyncio.sleep(retry_after)
      except groq.APITimeoutError:
        if attempt == max_retries:
          raise LLMProviderError(f"Request timed out: Request to LLM provider timed out after {self.timeout}s.")
        await asyncio.sleep(0.5 * (attempt + 1))
      except (groq.APIConnectionError, groq.APIStatusError) as e:
        if attempt == max_retries:
          raise LLMProviderError(f"API Connection or Status error from LLM provider: {str(e)}")
        await asyncio.sleep(0.5 * (attempt + 1))
      except Exception as e:
        raise LLMProviderError(f"LLM Provider execution failed: {str(e)}")


    raw_content = chat_completion.choices[0].message.content or ""

    structured_data = None
    if request.json_schema:
      import json
      try:
        structured_data = json.loads(raw_content)
      except json.JSONDecodeError as je:
        raise GroundingValidationError(
            f"Failed to parse model response as JSON: {raw_content}. Error: {str(je)}"
        )

    token_usage = None
    if chat_completion.usage:
      token_usage = {
          "prompt_tokens": chat_completion.usage.prompt_tokens,
          "completion_tokens": chat_completion.usage.completion_tokens,
          "total_tokens": chat_completion.usage.total_tokens
      }

    return LLMGenerationResponse(
        raw_response=raw_content,
        structured_output=structured_data,
        token_usage=token_usage,
        model_name=self.model
    )
