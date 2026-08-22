from dataclasses import dataclass
from typing import List, Set

from app.models.knowledge import KnowledgeEvidence
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.retrieval.base import EntityCandidate
from app.services.retrieval.scope_resolver import ResolvedScope


@dataclass
class EvidenceCandidate:
    """Represents a retrieved and validated evidence record with its status."""
    evidence: KnowledgeEvidence
    entity_id: str
    is_stale: bool


class EvidenceRetriever:
    """
    Retrieves, validates, and deduplicates KnowledgeEvidence records
    supporting a set of retrieved EntityCandidates.
    """

    def __init__(self, repo: KnowledgeRepository):
        self.repo = repo

    def retrieve_evidence(
        self,
        entity_candidates: List[EntityCandidate],
        resolved_scope: ResolvedScope
    ) -> List[EvidenceCandidate]:
        """
        Retrieves all evidence records supporting the given entity candidates.
        Deduplicates records by database ID and resolves stale flags.
        Returns a deterministically sorted list of EvidenceCandidates.
        """
        visited_ids: Set[str] = set()
        candidates: List[EvidenceCandidate] = []

        # Version isolation: candidates must match resolved_scope.version_id
        for candidate in entity_candidates:
            # Skip if the entity does not belong to the resolved version
            if candidate.entity.knowledge_version_id != resolved_scope.version_id:
                continue

            entity_id = candidate.entity.id
            evidence_records = self.repo.list_evidence_by_entity(entity_id)

            for ev in evidence_records:
                # Deduplication by stable database ID
                if ev.id in visited_ids:
                    continue
                visited_ids.add(ev.id)

                # Stale check: page_number is None indicates stale/missing block reference
                is_stale = ev.page_number is None

                candidates.append(
                    EvidenceCandidate(
                        evidence=ev,
                        entity_id=entity_id,
                        is_stale=is_stale
                    )
                )

        # Deterministic sorting: entity_id, non-stale first, page_number ascending, evidence ID alphabetically
        def get_sort_key(c: EvidenceCandidate):
            page = c.evidence.page_number if c.evidence.page_number is not None else float('inf')
            return (c.entity_id, c.is_stale, page, c.evidence.id)

        candidates.sort(key=get_sort_key)
        return candidates
