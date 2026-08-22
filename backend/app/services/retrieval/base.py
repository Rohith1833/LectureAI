from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, List, Protocol

from app.models.knowledge import KnowledgeEntity, KnowledgeRelationship
from app.schemas.retrieval import RetrievalRequest, RetrievalResult, RetrievalScope
from app.services.retrieval.query_normalizer import NormalizedQuery
from app.services.retrieval.scope_resolver import ResolvedScope


@dataclass
class EntityCandidate:
    """Represents a matched knowledge entity candidate before final ranking."""
    entity: KnowledgeEntity
    match_score: float
    match_reason: str
    matched_terms: List[str] = field(default_factory=list)
    hop_distance: int = 0


@dataclass
class RelationshipCandidate:
    """Represents a traversed relationship neighbor candidate."""
    relationship: KnowledgeRelationship
    source_entity: KnowledgeEntity
    target_entity: KnowledgeEntity
    hop_distance: int


class BaseRetriever(ABC):
    """
    Abstract Base Class representing the core contract for all retrieval strategy implementations.
    All Phase 7 retrievers (e.g. Lexical, Hybrid) must implement this interface.
    """

    @abstractmethod
    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        """
        Executes a retrieval operation scoped to a single document and finalized version.
        Returns a structured RetrievalResult context package containing scored entities,
        relationships, evidence coordinates, and verbatim source passages.
        """
        pass


class GraphTraversalStrategy(Protocol):
    """
    Protocol defining the contract for expanding entity search results across
    the versioned knowledge graph relationships.
    """

    def expand(
        self,
        entity_ids: List[str],
        scope: RetrievalScope,
        max_depth: int
    ) -> List[Any]:
        """
        Traverses relationships up to max_depth starting from source entity_ids.
        Returns a list of relationship candidates.
        """
        ...


class CandidateRetriever(Protocol):
    """
    Protocol representing a retriever component that generates matched entity
    candidates from a query and resolved scope before final ranking.
    """

    def retrieve_candidates(
        self,
        query: NormalizedQuery,
        resolved_scope: ResolvedScope,
        scope_filters: RetrievalScope
    ) -> List[EntityCandidate]:
        """
        Retrieves matching entity candidates from the repository based on query.
        """
        ...

