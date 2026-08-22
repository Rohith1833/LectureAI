import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import groq

from app.services.generation.base import LLMGenerationRequest
from app.services.generation.errors import LLMProviderError, GroundingValidationError
from app.services.generation.groq_provider import GroqProvider


class TestGenerationGroq(unittest.TestCase):
  """Focused tests verifying the GroqProvider adapter, request/response mapping, error handling, and timeout policies."""

  def setUp(self):
    self.api_key = "test-groq-key"
    self.model = "openai/gpt-oss-120b"
    self.request = LLMGenerationRequest(
        prompt="Grounding prompt text",
        system_instruction="System rule.",
        temperature=0.1,
        json_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"]
        }
    )

  def test_01_missing_api_key_raises_error(self):
    """Verify instantiating GroqProvider with empty credentials yields LLMProviderError."""
    with patch("app.services.generation.groq_provider.settings") as mock_settings:
      mock_settings.GROQ_API_KEY = None
      with self.assertRaises(LLMProviderError) as context:
        GroqProvider(api_key=None)
      self.assertIn("Missing API key", str(context.exception))

  @patch("app.services.generation.groq_provider.AsyncGroq")
  def test_02_successful_generation_mapping(self, mock_client_cls):
    """Verify request options, prompts, response schemas, and tokens map correctly under success."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    # Mock chat completion response
    mock_chat = AsyncMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    mock_client.chat.completions.create = mock_chat

    mock_choice = MagicMock()
    mock_choice.message = MagicMock()
    mock_choice.message.content = '{"answer": "Deterministic answer output."}'

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 50
    mock_usage.completion_tokens = 25
    mock_usage.total_tokens = 75

    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_completion.usage = mock_usage
    mock_chat.return_value = mock_completion

    provider = GroqProvider(api_key=self.api_key, model=self.model)
    response = asyncio.run(provider.generate(self.request))

    # Assert correct parameters were mapped to AsyncGroq call
    mock_chat.assert_called_once()
    kwargs = mock_chat.call_args[1]
    self.assertEqual(kwargs["model"], self.model)
    self.assertEqual(kwargs["temperature"], 0.1)
    self.assertEqual(kwargs["messages"][0], {"role": "system", "content": "System rule."})
    self.assertEqual(kwargs["messages"][1], {"role": "user", "content": "Grounding prompt text"})
    self.assertEqual(kwargs["response_format"]["type"], "json_schema")

    # Assert response mapped correctly
    self.assertEqual(response.model_name, self.model)
    self.assertEqual(response.structured_output, {"answer": "Deterministic answer output."})
    self.assertEqual(response.token_usage["prompt_tokens"], 50)
    self.assertEqual(response.token_usage["total_tokens"], 75)

  @patch("app.services.generation.groq_provider.AsyncGroq")
  def test_03_authentication_failure_mapping(self, mock_client_cls):
    """Verify Groq authentication exception maps to LLMProviderError without credential leaks."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_chat = AsyncMock(side_effect=groq.AuthenticationError(
        message="Invalid API Key",
        response=MagicMock(status_code=401),
        body=None
    ))
    mock_client.chat.completions.create = mock_chat

    provider = GroqProvider(api_key=self.api_key)
    with self.assertRaises(LLMProviderError) as context:
      asyncio.run(provider.generate(self.request))

    self.assertIn("Authentication failure", str(context.exception))
    self.assertNotIn(self.api_key, str(context.exception))

  @patch("app.services.generation.groq_provider.AsyncGroq")
  def test_04_rate_limit_mapping(self, mock_client_cls):
    """Verify Groq rate limit exception maps to LLMProviderError."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_chat = AsyncMock(side_effect=groq.RateLimitError(
        message="Too many requests",
        response=MagicMock(status_code=429),
        body=None
    ))
    mock_client.chat.completions.create = mock_chat

    provider = GroqProvider(api_key=self.api_key)
    with self.assertRaises(LLMProviderError) as context:
      asyncio.run(provider.generate(self.request))

    self.assertIn("Rate limit exceeded", str(context.exception))

  @patch("app.services.generation.groq_provider.AsyncGroq")
  def test_05_timeout_mapping(self, mock_client_cls):
    """Verify APITimeoutError maps to LLMProviderError."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_chat = AsyncMock(side_effect=groq.APITimeoutError(
        request=MagicMock()
    ))

    mock_client.chat.completions.create = mock_chat

    provider = GroqProvider(api_key=self.api_key)
    with self.assertRaises(LLMProviderError) as context:
      asyncio.run(provider.generate(self.request))

    self.assertIn("Request timed out", str(context.exception))

  @patch("app.services.generation.groq_provider.AsyncGroq")
  def test_06_invalid_request_mapping(self, mock_client_cls):
    """Verify BadRequestError maps to LLMProviderError."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_chat = AsyncMock(side_effect=groq.BadRequestError(
        message="Invalid model name",
        response=MagicMock(status_code=400),
        body=None
    ))
    mock_client.chat.completions.create = mock_chat

    provider = GroqProvider(api_key=self.api_key)
    with self.assertRaises(LLMProviderError) as context:
      asyncio.run(provider.generate(self.request))

    self.assertIn("Invalid request or model", str(context.exception))

  @patch("app.services.generation.groq_provider.AsyncGroq")
  def test_07_invalid_json_raises_validation_error(self, mock_client_cls):
    """Verify malformed JSON responses raise GroundingValidationError."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_chat = AsyncMock()
    mock_client.chat.completions.create = mock_chat

    mock_choice = MagicMock()
    mock_choice.message = MagicMock()
    mock_choice.message.content = "Malformed JSON { text"

    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_completion.usage = None
    mock_chat.return_value = mock_completion

    provider = GroqProvider(api_key=self.api_key)
    with self.assertRaises(GroundingValidationError) as context:
      asyncio.run(provider.generate(self.request))

    self.assertIn("Failed to parse model response as JSON", str(context.exception))

  def test_08_manual_smoke_test_skipped_by_default(self):
    """Manual smoke-test mapping verifies actual API connection. Skipped by default."""
    import os
    real_key = os.environ.get("GROQ_API_KEY_SMOKE_TEST")
    if not real_key or real_key == "test-groq-key":
      self.skipTest("Skipping real API smoke test. Set GROQ_API_KEY_SMOKE_TEST to run.")

    provider = GroqProvider(api_key=real_key)
    req = LLMGenerationRequest(
        prompt="Respond with exact text 'ACK'.",
        temperature=0.0
    )
    response = asyncio.run(provider.generate(req))
    self.assertEqual(response.raw_response.strip(), "ACK")
