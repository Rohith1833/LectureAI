import unittest
from pydantic import ValidationError

from app.schemas.generation import (
  GenerationRequest,
  GenerationOptions,
  ContextSource,
  Citation,
  GroundingStatus,
  GenerationClaim,
  GenerationContext,
  GenerationResult
)
from app.schemas.retrieval import RetrievalScope, RetrievalOptions, PassageSchema, RetrievalProvenance


class TestGenerationContracts(unittest.TestCase):
  """Tests verifying Pydantic request/response contracts and validation invariants in Phase 8A."""

  def test_01_generation_options_defaults(self):
    """Verify default generation options serialize correctly."""
    opts = GenerationOptions()
    self.assertEqual(opts.temperature, 0.0)
    self.assertEqual(opts.output_format, "TEXT")

  def test_02_generation_request_valid(self):
    """Verify a complete valid GenerationRequest is accepted."""
    req = GenerationRequest(
        query="Explain binary search complexity.",
        scope=RetrievalScope(document_id="doc_123", version_id="v_456"),
        retrieval_options=RetrievalOptions(top_k=5),
        generation_options=GenerationOptions(temperature=0.5, output_format="JSON"),
        conversation_context=[{"role": "user", "content": "hello"}]
    )
    self.assertEqual(req.query, "Explain binary search complexity.")
    self.assertEqual(req.scope.document_id, "doc_123")
    self.assertEqual(req.scope.version_id, "v_456")
    self.assertEqual(req.retrieval_options.top_k, 5)
    self.assertEqual(req.generation_options.temperature, 0.5)
    self.assertEqual(req.generation_options.output_format, "JSON")
    self.assertEqual(len(req.conversation_context), 1)

  def test_03_generation_request_empty_query_rejected(self):
    """Verify empty or whitespace-only queries are strictly rejected by the validator."""
    with self.assertRaises(ValidationError):
      GenerationRequest(
          query="",
          scope=RetrievalScope(document_id="doc_123"),
      )

    with self.assertRaises(ValidationError):
      GenerationRequest(
          query="   ",
          scope=RetrievalScope(document_id="doc_123"),
      )

  def test_04_context_source_generic_terminology(self):
    """Verify ContextSource represents concept/verbatim definitions generically without double-counting."""
    passage = PassageSchema(
        block_id="b1",
        page_number=1,
        text="Verbatim page text passage.",
        block_type="PARAGRAPH",
        section_title="Complexity Analysis",
        x0=10.0, y0=20.0, x1=100.0, y1=200.0
    )
    source = ContextSource(
        citation_id="S1",
        entity_id="ent_789",
        title="Binary Search",
        entity_type="ALGORITHM",
        content="Search algorithm running in logarithmic time.",
        passage=passage,
        provenance="NATIVE"
    )
    self.assertEqual(source.citation_id, "S1")
    self.assertEqual(source.entity_id, "ent_789")
    self.assertEqual(source.entity_type, "ALGORITHM")
    self.assertEqual(source.passage.text, "Verbatim page text passage.")
    self.assertEqual(source.provenance, "NATIVE")

  def test_05_citation_reference_integrity(self):
    """Verify Citation contract correctly maintains minimal citation ID links without text duplication."""
    cit = Citation(citation_id="S1")
    self.assertEqual(cit.citation_id, "S1")

  def test_06_generation_claim_grounding_states(self):
    """Verify GenerationClaim supports exact grounding enums."""
    claim = GenerationClaim(
        claim_id="cl_1",
        text="Binary search requires a sorted collection.",
        citation_ids=["S1", "S2"],
        grounding_status=GroundingStatus.SUPPORTED
    )
    self.assertEqual(claim.claim_id, "cl_1")
    self.assertEqual(claim.grounding_status, GroundingStatus.SUPPORTED)
    self.assertEqual(claim.citation_ids, ["S1", "S2"])

    # Test validator with invalid status
    with self.assertRaises(ValidationError):
      GenerationClaim(
          claim_id="cl_2",
          text="Assertion text.",
          citation_ids=[],
          grounding_status="INVALID_GROUNDING_STATUS"
      )

  def test_07_generation_result_mapping_integrity(self):
    """Verify GenerationResult captures parsed outputs, citations, and model metadata."""
    passage = PassageSchema(
        block_id="b1",
        page_number=2,
        text="Primary passage block text",
        block_type="PARAGRAPH",
        section_title=None,
        x0=0.0, y0=0.0, x1=1.0, y1=1.0
    )
    source = ContextSource(
        citation_id="S1",
        entity_id="ent_abc",
        title="Mock Entity",
        entity_type="CONCEPT",
        content="Mock content definition",
        passage=passage,
        provenance="OCR"
    )
    claim = GenerationClaim(
        claim_id="cl_1",
        text="Mock claim text.",
        citation_ids=["S1"],
        grounding_status=GroundingStatus.SUPPORTED
    )
    res = GenerationResult(
        answer="Mock natural language answer [S1].",
        claims=[claim],
        citations={"S1": source},
        overall_grounding_status=GroundingStatus.SUPPORTED,
        model_metadata={"latency_ms": 120.0, "tokens_used": 150}
    )
    self.assertEqual(res.overall_grounding_status, GroundingStatus.SUPPORTED)
    self.assertEqual(res.citations["S1"].title, "Mock Entity")
    self.assertEqual(res.model_metadata["tokens_used"], 150)
