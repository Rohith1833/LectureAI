from dataclasses import dataclass
from typing import Dict, List, Set

from app.schemas.retrieval import RetrievalScope
from app.services.retrieval.base import EntityCandidate, RelationshipCandidate
from app.services.retrieval.evidence_retriever import EvidenceCandidate
from app.services.retrieval.passage_retriever import PassageCandidate
from app.services.retrieval.query_normalizer import NormalizedQuery


@dataclass(frozen=True)
class RankingWeights:
    """
    Configuration coefficients for combining multiple retrieval signals.
    Enforces that weights sum to exactly 1.0 (within float precision).
    """
    title: float = 0.30
    content: float = 0.10
    coverage: float = 0.15
    type: float = 0.10
    relationship: float = 0.10
    evidence: float = 0.10
    passage: float = 0.10
    confidence: float = 0.05

    def validate(self) -> None:
        """Raise ValueError if weights do not sum to 1.0."""
        total = (
            self.title + self.content + self.coverage + self.type +
            self.relationship + self.evidence + self.passage + self.confidence
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Ranking weights must sum to 1.0, got {total}")


@dataclass
class RetrievalScore:
    """Detailed relevance score decomposition for an entity candidate."""
    entity_id: str
    title_score: float
    content_score: float
    coverage_score: float
    type_score: float
    relationship_score: float
    evidence_score: float
    passage_score: float
    confidence_score: float
    total_score: float


class Ranker:
    """
    Evaluates and scores EntityCandidates based on match metrics, query term coverage,
    preferred entity types, graph hops, evidence and passage states, and relationship confidence.
    """

    def score_candidates(
        self,
        entity_candidates: List[EntityCandidate],
        relationship_candidates: List[RelationshipCandidate],
        evidence_candidates: List[EvidenceCandidate],
        passage_candidates: List[PassageCandidate],
        normalized_query: NormalizedQuery,
        scope_filters: RetrievalScope,
        weights: RankingWeights = RankingWeights()
    ) -> List[RetrievalScore]:
        """
        Computes relevance scores for entity candidates and sorts them deterministically.
        """
        # Validate weights configuration
        weights.validate()

        # Build helper maps for efficient feature extraction
        evidence_by_entity: Dict[str, List[EvidenceCandidate]] = {}
        for ev in evidence_candidates:
            evidence_by_entity.setdefault(ev.entity_id, []).append(ev)

        max_confidence_by_entity: Dict[str, float] = {}
        for rel_cand in relationship_candidates:
            rel = rel_cand.relationship
            conf = rel.confidence if rel.confidence is not None else 1.0

            src_id = rel.source_entity_id
            max_confidence_by_entity[src_id] = max(max_confidence_by_entity.get(src_id, 0.0), conf)

            tgt_id = rel.target_entity_id
            max_confidence_by_entity[tgt_id] = max(max_confidence_by_entity.get(tgt_id, 0.0), conf)

        has_passage_by_entity: Set[str] = set()
        for pass_cand in passage_candidates:
            for ent_id in pass_cand.entity_ids:
                has_passage_by_entity.add(ent_id)

        scores: List[RetrievalScore] = []
        cand_map: Dict[str, EntityCandidate] = {}

        for cand in entity_candidates:
            entity = cand.entity
            ent_id = entity.id
            cand_map[ent_id] = cand

            # 1. Title match score (Lexical match reason)
            if cand.match_reason == "title_exact":
                title_score = 1.0
            elif cand.match_reason == "title_prefix":
                title_score = 0.8
            elif cand.match_reason == "title_contains":
                title_score = 0.6
            elif cand.match_reason == "title_term":
                title_score = 0.4
            else:
                title_score = 0.0

            # 2. Content match score (prevent double-counting when content is identical to title)
            content_stripped = (entity.content or "").strip().lower()
            title_stripped = (entity.title or "").strip().lower()

            if not content_stripped or content_stripped == title_stripped:
                content_score = 0.0
            else:
                if cand.match_reason == "content_contains":
                    content_score = 1.0
                else:
                    content_score = 0.0
                    for term in normalized_query.terms:
                        if term in content_stripped:
                            content_score = 1.0
                            break

            # 3. Query term coverage score (explicit configurable ranking signal)
            total_terms = len(set(normalized_query.terms))
            if total_terms > 0:
                matched_terms = len(set(cand.matched_terms))
                coverage_score = matched_terms / total_terms
            else:
                coverage_score = 0.0

            # 4. Preferred type score
            if scope_filters.entity_types and entity.entity_type in scope_filters.entity_types:
                type_score = 1.0
            else:
                type_score = 0.0

            # 5. Graph neighbor score (attenuated by hop distance)
            graph_score = 1.0 / (cand.hop_distance + 1)

            # 6. Evidence availability score (1.0 if active evidence exists, 0.5 if only stale)
            evs = evidence_by_entity.get(ent_id, [])
            if any(not ev.is_stale for ev in evs):
                evidence_score = 1.0
            elif any(ev.is_stale for ev in evs):
                evidence_score = 0.5
            else:
                evidence_score = 0.0

            # 7. Passage availability score
            passage_score = 1.0 if ent_id in has_passage_by_entity else 0.0

            # 8. Bounded relationship confidence score
            confidence_score = max_confidence_by_entity.get(ent_id, 0.0)

            # Calculate total weighted score
            total_score = (
                (weights.title * title_score) +
                (weights.content * content_score) +
                (weights.coverage * coverage_score) +
                (weights.type * type_score) +
                (weights.relationship * graph_score) +
                (weights.evidence * evidence_score) +
                (weights.passage * passage_score) +
                (weights.confidence * confidence_score)
            )

            scores.append(
                RetrievalScore(
                    entity_id=ent_id,
                    title_score=title_score,
                    content_score=content_score,
                    coverage_score=coverage_score,
                    type_score=type_score,
                    relationship_score=graph_score,
                    evidence_score=evidence_score,
                    passage_score=passage_score,
                    confidence_score=confidence_score,
                    total_score=total_score
                )
            )

        # Deterministic sorting policy
        def get_sort_key(s: RetrievalScore) -> tuple:
            cand = cand_map[s.entity_id]
            return (-s.total_score, -cand.match_score, cand.hop_distance, cand.entity.stable_id, cand.entity.id)

        scores.sort(key=get_sort_key)
        return scores
