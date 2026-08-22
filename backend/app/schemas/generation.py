from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

from app.schemas.retrieval import PassageSchema, RetrievalProvenance, RetrievalScope, RetrievalOptions


class GenerationOptions(BaseModel):
  """Simple configuration options for AI response generation."""
  temperature: float = Field(0.0, ge=0.0, le=2.0, description="Sampling temperature.")
  output_format: str = Field("TEXT", description="Format constraints: TEXT, JSON, etc.")


class GenerationRequest(BaseModel):
  """Payload submitted to request grounded answer generation."""
  query: str = Field(..., min_length=1, max_length=2048, description="User search query.")
  scope: RetrievalScope
  retrieval_options: RetrievalOptions = Field(default_factory=RetrievalOptions)
  generation_options: GenerationOptions = Field(default_factory=GenerationOptions)
  conversation_context: Optional[List[Dict[str, str]]] = Field(None, description="Optional dialogue context history.")

  @field_validator("query")
  @classmethod
  def validate_query_not_empty(cls, v: str) -> str:
    if not v or not v.strip():
      raise ValueError("Query must not be empty or whitespace-only.")
    return v


class ContextSource(BaseModel):
  """A single grounding source resolved for prompting context."""
  citation_id: str = Field(..., description="Stable context citation key, e.g. S1, S2.")
  entity_id: str = Field(..., description="Referenced KnowledgeEntity ID.")
  title: str = Field(..., description="Title of the knowledge entity.")
  entity_type: str = Field(..., description="Classification category (e.g. CONCEPT, DEFINITION).")
  content: str = Field(..., description="Generic text content of the entity.")
  passage: Optional[PassageSchema] = Field(None, description="Verbatim resolved passage from the document block layer.")
  provenance: Optional[str] = Field(None, description="Authoritative origin log for layout evidence.")


class Citation(BaseModel):
  """Minimal reference mapping a claim citation ID back to a ContextSource."""
  citation_id: str = Field(..., description="Target citation identifier.")


class GroundingStatus(str, Enum):
  """Evaluation status of individual claim grounding validation checks."""
  SUPPORTED = "SUPPORTED"
  PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
  UNSUPPORTED = "UNSUPPORTED"
  INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"


class GenerationClaim(BaseModel):
  """A structured informational statement extracted from generated text."""
  claim_id: str = Field(..., description="Unique ID within the result scope.")
  text: str = Field(..., description="Asserted claim text.")
  citation_ids: List[str] = Field(default_factory=list, description="Associated context citation source IDs.")
  grounding_status: GroundingStatus = Field(..., description="Resolved validation state.")


class GenerationContext(BaseModel):
  """Aggregated grounding sources packaged for PromptBuilder compilation."""
  sources: List[ContextSource] = Field(default_factory=list, description="Ordered grounding sources.")
  provenance: RetrievalProvenance = Field(..., description="Diagnostic details trace.")


class GenerationResult(BaseModel):
  """Unified grounded response containing answers, citations, and grounding metadata."""
  answer: str = Field(..., description="Grounded natural-language answer text.")
  claims: List[GenerationClaim] = Field(default_factory=list, description="List of parsed claims.")
  citations: Dict[str, ContextSource] = Field(default_factory=dict, description="Citations mapping ID -> Source details.")
  overall_grounding_status: GroundingStatus = Field(..., description="Consolidated overall status.")
  model_metadata: Optional[Dict[str, Any]] = Field(None, description="Metadata such as latency or tokens.")
