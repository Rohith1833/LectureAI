from typing import List, Set
from app.schemas.generation import ContextSource, GenerationContext
from app.schemas.retrieval import RetrievalResult


class ContextBuilder:
  """Transforms a RetrievalResult into a consolidated model-ready GenerationContext."""

  def __init__(self, max_chars: int = 16000):
    self.max_chars = max_chars

  def build(self, result: RetrievalResult) -> GenerationContext:
    """Consolidates retrieved candidates, deduplicates passages, and packages context."""
    if not result.entities:
      return GenerationContext(sources=[], provenance=result.provenance)

    # Maintain ranked order. For ties, sort deterministically by stable_id then id.
    sorted_entities = sorted(
        result.entities,
        key=lambda x: (
            -x.score,
            x.entity.stable_id or "",
            x.entity.id or ""
        )
    )

    sources: List[ContextSource] = []
    seen_entity_ids: Set[str] = set()
    seen_block_ids: Set[str] = set()
    citation_counter = 1

    current_chars = 0

    for candidate in sorted_entities:
      entity = candidate.entity
      entity_id = entity.id or ""

      # 1. Add Entity Content Source if not seen
      if entity_id and entity_id not in seen_entity_ids:
        source_content = entity.content or ""
        source_len = len(entity.title or "") + len(source_content)

        if current_chars + source_len <= self.max_chars:
          seen_entity_ids.add(entity_id)
          sources.append(
              ContextSource(
                  citation_id=f"S{citation_counter}",
                  entity_id=entity_id,
                  title=entity.title,
                  entity_type=entity.entity_type,
                  content=source_content,
                  passage=None,
                  provenance="ENTITY_CONTENT"
              )
          )
          current_chars += source_len
          citation_counter += 1

      # 2. Add Passage Sources
      for passage in candidate.passages:
        block_id = passage.block_id

        # Skip duplicate passages within the document/version scope
        if block_id in seen_block_ids:
          continue

        passage_len = len(entity.title or "") + len(passage.text or "")
        if current_chars + passage_len <= self.max_chars:
          seen_block_ids.add(block_id)
          sources.append(
              ContextSource(
                  citation_id=f"S{citation_counter}",
                  entity_id=entity_id,
                  title=entity.title,
                  entity_type=entity.entity_type,
                  content=entity.content or "",
                  passage=passage,
                  provenance=passage.block_type or "PASSAGE"
              )
          )
          current_chars += passage_len
          citation_counter += 1

    return GenerationContext(sources=sources, provenance=result.provenance)
