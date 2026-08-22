from typing import List, Optional

from app.repositories.knowledge_repository import KnowledgeRepository
from app.schemas.retrieval import RetrievalScope
from app.services.retrieval.base import EntityCandidate
from app.services.retrieval.query_normalizer import NormalizedQuery
from app.services.retrieval.scope_resolver import ResolvedScope


class LexicalRetriever:
    """
    Retrieves matching KnowledgeEntity candidates from a finalized KnowledgeVersion
    using case-insensitive substring, prefix, and term-matching strategies.
    """

    def __init__(self, repo: KnowledgeRepository):
        self.repo = repo

    def retrieve_candidates(
        self,
        query: NormalizedQuery,
        resolved_scope: ResolvedScope,
        scope_filters: RetrievalScope
    ) -> List[EntityCandidate]:
        """
        Queries the repository for entities matching the terms in NormalizedQuery.
        Scores and classifies them according to title/content match hierarchy.
        Returns a deterministically ordered list of EntityCandidates.
        """
        # Fetch entities from repository filtered by version and scope.entity_types
        entity_types = scope_filters.entity_types
        entities = self.repo.search_entities(
            knowledge_version_id=resolved_scope.version_id,
            terms=query.terms,
            entity_types=entity_types
        )

        candidates: List[EntityCandidate] = []
        query_normalized = query.normalized

        for entity in entities:
            title_lower = entity.title.lower()
            content_lower = (entity.content or "").lower()

            # Determine strongest match reason and score
            if title_lower == query_normalized:
                match_reason = "title_exact"
                match_score = 1.0
                matched_terms = query.terms
            elif title_lower.startswith(query_normalized):
                match_reason = "title_prefix"
                match_score = 0.8
                matched_terms = [t for t in query.terms if t in title_lower]
            elif query_normalized in title_lower:
                match_reason = "title_contains"
                match_score = 0.6
                matched_terms = [t for t in query.terms if t in title_lower]
            else:
                title_matched = [t for t in query.terms if t in title_lower]
                if title_matched:
                    match_reason = "title_term"
                    match_score = 0.4
                    matched_terms = title_matched
                else:
                    content_matched = [t for t in query.terms if t in content_lower]
                    if query_normalized in content_lower or content_matched:
                        match_reason = "content_contains"
                        match_score = 0.2
                        matched_terms = content_matched if content_matched else [t for t in query.terms if t in content_lower]
                    else:
                        # Fallback case (should be unreachable due to repository filter)
                        continue

            candidates.append(
                EntityCandidate(
                    entity=entity,
                    match_score=match_score,
                    match_reason=match_reason,
                    matched_terms=matched_terms
                )
            )

        # Deterministic sorting: higher match_score first, then stable_id alphabetically
        candidates.sort(key=lambda c: (-c.match_score, c.entity.stable_id))
        return candidates
