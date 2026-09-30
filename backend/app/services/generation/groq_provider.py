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
      timeout: float = 30.0,
      max_retries: int = 2,
      base_backoff: float = 1.0,
      max_retry_wait_budget: float = 15.0
  ):
    self.api_key = api_key or settings.GROQ_API_KEY
    self.model = model or settings.GROQ_MODEL
    self.timeout = timeout
    self.max_retries = max_retries
    self.base_backoff = base_backoff
    self.max_retry_wait_budget = max_retry_wait_budget

    if not self.api_key:
      raise LLMProviderError("Missing API key: GROQ_API_KEY environment variable is not set.")

    # Initialize AsyncGroq client with max_retries=0 so SDK internal retries do not multiply with our bounded loop
    self.client = AsyncGroq(api_key=self.api_key, timeout=self.timeout, max_retries=0)

  async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
    """Translates LLMGenerationRequest into Groq chat completion and returns LLMGenerationResponse.
    
    Provider bounds:
    - Per-attempt timeout: self.timeout (default 30.0s)
    - Max attempts: self.max_retries + 1 (default 3 attempts)
    - Exponential backoff: base_backoff * (2 ** attempt) (1.0s, 2.0s)
    - Retry-After wait budget: max_retry_wait_budget (default 15.0s). If provider requests > budget, halts immediately.
    - Max total duration worst-case: (attempts * timeout) + (retries * max_wait_budget) = (3 * 30) + (2 * 15) = 120s.
    """
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

    for attempt in range(self.max_retries + 1):
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
        if attempt == self.max_retries:
          raise LLMProviderError(f"Rate limit exceeded on LLM provider after {self.max_retries + 1} attempts.")
        retry_after = self.base_backoff * (2 ** attempt)
        if hasattr(e, "response") and e.response is not None:
          header_val = e.response.headers.get("retry-after")
          if header_val:
            try:
              parsed_val = float(header_val)
              if parsed_val > self.max_retry_wait_budget:
                raise LLMProviderError(
                    f"Rate limit exceeded: Provider requested Retry-After of {parsed_val}s, "
                    f"which exceeds maximum permitted retry-wait budget of {self.max_retry_wait_budget}s. Please retry later."
                )
              retry_after = parsed_val
            except ValueError:
              pass
        await asyncio.sleep(retry_after)
      except groq.APITimeoutError:
        if attempt == self.max_retries:
          raise LLMProviderError(f"Request timed out: Request to LLM provider timed out after {self.timeout}s.")
        await asyncio.sleep(self.base_backoff * (2 ** attempt))
      except (groq.APIConnectionError, groq.APIStatusError) as e:
        if attempt == self.max_retries:
          raise LLMProviderError(f"API Connection or Status error from LLM provider: {str(e)}")
        await asyncio.sleep(self.base_backoff * (2 ** attempt))
      except Exception as e:
        if isinstance(e, LLMProviderError):
          raise
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
