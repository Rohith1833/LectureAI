from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.retrieval import PassageSchema, RetrievalProvenance, RetrievalScope, RetrievalOptions


class GenerationMode(str, Enum):
  """Available generation modes for the AI generation pipeline."""
  QA = "QA"
  EXPLANATION = "EXPLANATION"
  SUMMARY = "SUMMARY"
  COMPARISON = "COMPARISON"
  STUDY_GUIDE = "STUDY_GUIDE"


class ComparisonOptions(BaseModel):
  """Structured comparison parameters specifying targets and optional dimensions."""
  subjects: List[str] = Field(..., description="Target concept/entity titles to compare.")
  dimensions: Optional[List[str]] = Field(None, description="Optional properties/dimensions to compare across subjects.")

  @field_validator("subjects")
  @classmethod
  def validate_subjects_not_empty(cls, v: List[str]) -> List[str]:
    if not v or len(v) < 2:
      raise ValueError("Comparison requires at least 2 subjects.")
    for s in v:
      if not s or not s.strip():
        raise ValueError("Subject titles must not be empty or whitespace-only.")
    return v


class StudyGuideOptions(BaseModel):
  """Structured study guide parameters specifying target questions and difficulty."""
  question_count: Optional[int] = Field(5, ge=1, le=10, description="Number of review questions to generate (1 to 10).")
  difficulty: Optional[str] = Field("intermediate", description="Target difficulty: basic, intermediate, advanced.")

  @field_validator("difficulty")
  @classmethod
  def validate_difficulty(cls, v: Optional[str]) -> Optional[str]:
    if v is not None and v not in ("basic", "intermediate", "advanced"):
      raise ValueError("Difficulty must be one of: basic, intermediate, advanced.")
    return v


class GenerationOptions(BaseModel):
  """Simple configuration options for AI response generation."""
  temperature: float = Field(0.0, ge=0.0, le=2.0, description="Sampling temperature.")
  output_format: str = Field("TEXT", description="Format constraints: TEXT, JSON, etc.")


class ConversationTurn(BaseModel):
  """Single turn of conversational dialogue history."""
  role: str = Field(..., description="Message author role: USER or ASSISTANT")
  content: str = Field(..., description="Message text content")
  sequence: Optional[int] = Field(None, description="Monotonic sequence number in the conversation")


class GenerationRequest(BaseModel):
  """Payload submitted to request grounded answer generation."""
  query: str = Field(..., min_length=1, max_length=2048, description="User search query.")
  scope: RetrievalScope
  mode: GenerationMode = Field(default=GenerationMode.QA, description="Active generation mode.")
  retrieval_options: RetrievalOptions = Field(default_factory=RetrievalOptions)
  generation_options: GenerationOptions = Field(default_factory=GenerationOptions)
  comparison_options: Optional[ComparisonOptions] = Field(None, description="Optional comparison configuration.")
  study_options: Optional[StudyGuideOptions] = Field(None, description="Optional study guide configuration.")
  conversation_id: Optional[str] = Field(None, description="Optional ID of the persistent conversation session.")
  conversation_context: Optional[List[Dict[str, str]]] = Field(None, description="Optional dialogue context history.")

  @field_validator("query")
  @classmethod
  def validate_query_not_empty(cls, v: str) -> str:
    if not v or not v.strip():
      raise ValueError("Query must not be empty or whitespace-only.")
    return v

  @model_validator(mode="after")
  def validate_comparison_request(self) -> "GenerationRequest":
    if self.mode == GenerationMode.COMPARISON:
      if not self.comparison_options or not self.comparison_options.subjects:
        raise ValueError("Comparison mode requires comparison_options with explicitly specified subjects.")
    return self


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
  conversation_history: List[ConversationTurn] = Field(default_factory=list, description="Ordered previous conversational turns (not citation sources).")


class GenerationResult(BaseModel):
  """Unified grounded response containing answers, citations, and grounding metadata."""
  mode: GenerationMode = Field(default=GenerationMode.QA, description="Active generation mode.")
  answer: str = Field(..., description="Grounded natural-language answer text.")
  structured_output: Optional[Dict[str, Any]] = Field(None, description="Raw structured mode-specific output JSON.")
  claims: List[GenerationClaim] = Field(default_factory=list, description="List of parsed claims.")
  citations: Dict[str, ContextSource] = Field(default_factory=dict, description="Citations mapping ID -> Source details.")
  overall_grounding_status: GroundingStatus = Field(..., description="Consolidated overall status.")
  model_metadata: Optional[Dict[str, Any]] = Field(None, description="Metadata such as latency or tokens.")
