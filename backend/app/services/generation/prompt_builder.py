from app.schemas.generation import GenerationContext, GenerationRequest
from app.services.generation.base import LLMGenerationRequest
from app.services.generation.modes.registry import strategy_registry


class PromptBuilder:
  """Centralizes prompt engineering templates and system/grounding instructions."""

  # Backwards compatibility class variables mapping to QAModeStrategy
  from app.services.generation.modes.qa import QAModeStrategy
  _qa = QAModeStrategy()
  SYSTEM_INSTRUCTION = _qa.system_instruction
  GROUNDING_INSTRUCTIONS = _qa.grounding_instructions
  OUTPUT_REQUIREMENTS = _qa.output_requirements

  def build(self, request: GenerationRequest, context: GenerationContext) -> LLMGenerationRequest:
    """Compiles a GenerationRequest and GenerationContext into a deterministic LLMGenerationRequest."""
    strategy = strategy_registry.get(request.mode)

    # 1. Format context sources
    formatted_sources = []
    for source in context.sources:
      source_block = (
          f"Source ID: {source.citation_id}\n"
          f"Title: {source.title} (Type: {source.entity_type})\n"
          f"Content: {source.content}\n"
      )
      if source.passage:
        source_block += f"Verbatim Passage: {source.passage.text}\n"
      source_block += "---"
      formatted_sources.append(source_block)

    context_str = "\n".join(formatted_sources) if formatted_sources else "NO GROUNDING CONTEXT AVAILABLE."

    # 2. Format conversation history if present
    history_block = ""
    if context.conversation_history:
      history_lines = []
      for turn in context.conversation_history:
        history_lines.append(f"{turn.role}: {turn.content}")
      history_block = "PREVIOUS CONVERSATION HISTORY:\n" + "\n".join(history_lines) + "\n\n"

    # 3. Build structured prompt
    prompt = (
        f"{strategy.grounding_instructions}\n\n"
        f"SUPPLIED CONTEXT SOURCES:\n"
        f"{context_str}\n\n"
        f"{history_block}"
        f"{strategy.output_requirements}\n\n"
        f"USER QUERY: {request.query}"
    )

    return LLMGenerationRequest(
        prompt=prompt,
        system_instruction=strategy.system_instruction,
        temperature=request.generation_options.temperature,
        json_schema=strategy.json_schema
    )
