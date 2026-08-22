from typing import Dict, List, Set

from app.models.knowledge import KnowledgeVersion
from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.schemas.knowledge import (
    KnowledgeEntitySchema,
    KnowledgeEvidenceSchema,
    KnowledgeRelationshipSchema,
)
from app.schemas.retrieval import (
    PassageSchema,
    RetrievalProvenance,
    RetrievalRequest,
    RetrievalResult,
    RetrievedEntity,
)
from app.services.retrieval.base import BaseRetriever, EntityCandidate
from app.services.retrieval.evidence_retriever import EvidenceRetriever, EvidenceCandidate
from app.services.retrieval.graph_expander import GraphExpander
from app.services.retrieval.lexical_retriever import LexicalRetriever
from app.services.retrieval.passage_retriever import PassageRetriever, PassageCandidate
from app.services.retrieval.query_normalizer import QueryNormalizer
from app.services.retrieval.ranker import Ranker, RankingWeights, RetrievalScore
from app.services.retrieval.scope_resolver import ScopeResolver


class RetrievalService(BaseRetriever):
    """
    Orchestrates query parsing, scope resolution, candidate retrieval, graph expansion,
    evidence coordinates gathering, passage mapping, and candidate ranking.
    Packages the final ranked context into a RetrievalResult payload.
    """

    def __init__(
        self,
        knowledge_repo: KnowledgeRepository,
        document_repo: DocumentRepository,
        weights: RankingWeights = RankingWeights()
    ):
        self.repo = knowledge_repo
        self.doc_repo = document_repo
        self.query_normalizer = QueryNormalizer()
        self.scope_resolver = ScopeResolver(knowledge_repo)
        self.lexical_retriever = LexicalRetriever(knowledge_repo)
        self.graph_expander = GraphExpander(knowledge_repo)
        self.evidence_retriever = EvidenceRetriever(knowledge_repo)
        self.passage_retriever = PassageRetriever(document_repo)
        self.ranker = Ranker()
        self.weights = weights

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        """
        Executes a deterministic retrieval pipeline.
        Rejects unsupported strategies explicitly.
        """
        # Validate and reject unsupported strategies
        strategy = request.options.strategy
        if strategy != "LEXICAL":
            raise ValueError(f"Strategy '{strategy}' is not supported. Only 'LEXICAL' is currently implemented.")

        # 1. Normalize query
        normalized_query = self.query_normalizer.normalize(request.query)

        # 2. Resolve scope
        resolved_scope = self.scope_resolver.resolve(request.scope)

        # 3. Retrieve lexical candidates (seed hits)
        lexical_cands = self.lexical_retriever.retrieve_candidates(
            query=normalized_query,
            resolved_scope=resolved_scope,
            scope_filters=request.scope
        )

        # 4. Expand graph via BFS
        max_depth = request.options.relationship_depth if request.options.include_relationships else 0
        expansion_result = self.graph_expander.expand(
            lexical_candidates=lexical_cands,
            resolved_scope=resolved_scope,
            scope_filters=request.scope,
            max_depth=max_depth
        )
        entity_candidates = expansion_result.entities
        relationship_candidates = expansion_result.relationships

        # 5. Retrieve evidence coordinates
        if request.options.include_evidence:
            evidence_candidates = self.evidence_retriever.retrieve_evidence(
                entity_candidates=entity_candidates,
                resolved_scope=resolved_scope
            )
        else:
            evidence_candidates = []

        # 6. Retrieve source block passages
        if request.options.include_passages and request.options.include_evidence:
            passage_candidates = self.passage_retriever.retrieve_passages(
                evidence_candidates=evidence_candidates,
                resolved_scope=resolved_scope
            )
        else:
            passage_candidates = []

        # 7. Score and sort candidates deterministically
        scores = self.ranker.score_candidates(
            entity_candidates=entity_candidates,
            relationship_candidates=relationship_candidates,
            evidence_candidates=evidence_candidates,
            passage_candidates=passage_candidates,
            normalized_query=normalized_query,
            scope_filters=request.scope,
            weights=self.weights
        )

        # 8. Build lookup maps for packaging
        entity_cand_map = {c.entity.id: c for c in entity_candidates}
        score_map = {s.entity_id: s.total_score for s in scores}

        # Filter relationships, evidence, and passages for each entity
        packaged_entities: List[RetrievedEntity] = []
        for s in scores:
            ent_id = s.entity_id
            cand = entity_cand_map[ent_id]
            entity = cand.entity

            # Convert relationships
            outgoing_rels = [
                KnowledgeRelationshipSchema.model_validate(r.relationship)
                for r in relationship_candidates
                if r.relationship.source_entity_id == ent_id
            ]
            incoming_rels = [
                KnowledgeRelationshipSchema.model_validate(r.relationship)
                for r in relationship_candidates
                if r.relationship.target_entity_id == ent_id
            ]

            # Convert evidence
            ev_list = [
                KnowledgeEvidenceSchema.model_validate(e.evidence)
                for e in evidence_candidates
                if e.entity_id == ent_id
            ]

            # Convert passages
            pass_list = [
                PassageSchema(
                    block_id=p.block_id,
                    page_number=p.page_number,
                    text=p.text,
                    block_type=p.block_type,
                    section_title=p.section_title,
                    x0=p.x0,
                    y0=p.y0,
                    x1=p.x1,
                    y1=p.y1
                )
                for p in passage_candidates
                if ent_id in p.entity_ids
            ]

            packaged_entities.append(
                RetrievedEntity(
                    entity=KnowledgeEntitySchema.model_validate(entity),
                    score=s.total_score,
                    match_reason=cand.match_reason,
                    outgoing_relationships=outgoing_rels,
                    incoming_relationships=incoming_rels,
                    evidence=ev_list,
                    passages=pass_list
                )
            )

        # 9. Apply Top-K truncation and determinehas_more
        total_candidates_considered = len(packaged_entities)
        top_k = request.options.top_k
        has_more = total_candidates_considered > top_k
        truncated_entities = packaged_entities[:top_k]

        # 10. Query graph properties for provenance
        version = self.repo.db.query(KnowledgeVersion).filter(KnowledgeVersion.id == resolved_scope.version_id).first()
        approval_version = version.snapshot.approval_version if (version and version.snapshot) else 0

        total_entity_count = self.repo.count_entities(resolved_scope.version_id)

        provenance = RetrievalProvenance(
            knowledge_version_id=resolved_scope.version_id,
            approval_version=approval_version,
            document_id=resolved_scope.document_id,
            strategy_used=strategy,
            query_terms=normalized_query.terms,
            total_candidates_considered=total_candidates_considered
        )

        return RetrievalResult(
            query=normalized_query.raw,
            scope=request.scope,

            provenance=provenance,
            entities=truncated_entities,
            total_entity_count=total_entity_count,
            has_more=has_more
        )
