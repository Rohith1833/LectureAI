from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

from app.schemas.knowledge import (
    KnowledgeEntitySchema,
    KnowledgeRelationshipSchema,
    KnowledgeEvidenceSchema
)


class RetrievalScope(BaseModel):
    """Defines the restricted single-document and finalized KnowledgeVersion search boundaries."""
    document_id: str = Field(..., description="Canonical document identifier to search within.")
    version_id: Optional[str] = Field(None, description="Explicit finalized KnowledgeVersion UUID. If None, resolves to latest.")
    entity_types: Optional[List[str]] = Field(None, description="Optional filter to restrict retrieval to specific entity types.")
    relationship_types: Optional[List[str]] = Field(None, description="Optional filter to restrict relationship expansion types.")


class RetrievalOptions(BaseModel):
    """Configuration options controlling retrieval strategy, depth, and output formatting."""
    top_k: int = Field(10, ge=1, le=100, description="Maximum number of retrieved entities to return.")
    include_relationships: bool = Field(True, description="Whether to fetch and attach entity relationships.")
    include_evidence: bool = Field(True, description="Whether to fetch and attach entity evidence coordinates.")
    include_passages: bool = Field(True, description="Whether to fetch and attach verbatim document passages.")
    relationship_depth: int = Field(1, ge=0, le=3, description="Maximum graph hops to traverse for relationship expansion.")
    strategy: str = Field("LEXICAL", description="Retrieval strategy: LEXICAL, etc.")


class RetrievalRequest(BaseModel):
    """Client payload specifying the search query and scoping parameters."""
    query: str = Field(..., min_length=1, max_length=2048, description="Verbatim text search query.")
    scope: RetrievalScope
    options: RetrievalOptions = Field(default_factory=RetrievalOptions)

    @field_validator("query")
    @classmethod
    def validate_query_not_empty_or_whitespace(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Query must not be empty or whitespace-only.")
        return v


class PassageSchema(BaseModel):
    """Represents a retrieved verbatim document page block passage with coordinates."""
    block_id: str = Field(..., description="Primary identifier of the source document block.")
    page_number: int = Field(..., description="1-indexed source document page number.")
    text: str = Field(..., description="Verbatim text contents of the page block.")
    block_type: str = Field(..., description="Layout element category (e.g. PARAGRAPH, HEADING).")
    section_title: Optional[str] = Field(None, description="Resolved section heading hierarchy details.")
    x0: float = Field(..., description="Bounding box horizontal start coordinate.")
    y0: float = Field(..., description="Bounding box vertical start coordinate.")
    x1: float = Field(..., description="Bounding box horizontal end coordinate.")
    y1: float = Field(..., description="Bounding box vertical end coordinate.")


class RetrievedEntity(BaseModel):
    """A matched knowledge entity packaged with its ranking score, relationships, evidence, and passages."""
    entity: KnowledgeEntitySchema
    score: float = Field(..., description="Deterministic relevance score computed by the ranker.")
    match_reason: str = Field(..., description="Explanatory code detailing why this entity matched the query.")
    outgoing_relationships: List[KnowledgeRelationshipSchema] = Field(default_factory=list, description="Traversed outbound relationships.")
    incoming_relationships: List[KnowledgeRelationshipSchema] = Field(default_factory=list, description="Traversed inbound relationships.")
    evidence: List[KnowledgeEvidenceSchema] = Field(default_factory=list, description="Resolved layout evidence coordinates.")
    passages: List[PassageSchema] = Field(default_factory=list, description="Resolved source passage block data.")


class RetrievalProvenance(BaseModel):
    """Diagnostic details logging version boundaries and query constraints used during execution."""
    knowledge_version_id: str = Field(..., description="Resolved KnowledgeVersion UUID searched.")
    approval_version: int = Field(..., description="Authoritative approval revision from AcademicGraphSnapshot.")
    document_id: str = Field(..., description="Canonical document ID searched.")
    strategy_used: str = Field(..., description="Selected retrieval strategy (e.g. LEXICAL).")
    query_terms: List[str] = Field(default_factory=list, description="Normalized search query terms.")
    total_candidates_considered: int = Field(..., description="Total candidates matched before top-k truncation.")


class RetrievalResult(BaseModel):
    """The structured retrieval context package delivered to Phase 8 reasoning layers."""
    query: str = Field(..., description="Original normalized client search query.")
    scope: RetrievalScope
    provenance: RetrievalProvenance
    entities: List[RetrievedEntity] = Field(default_factory=list, description="Ranked retrieved entity results.")
    total_entity_count: int = Field(..., description="Total entities present in the target version graph.")
    has_more: bool = Field(..., description="Flag indicating if matches were truncated by top_k.")
