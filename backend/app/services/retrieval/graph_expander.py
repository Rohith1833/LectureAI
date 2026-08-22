from dataclasses import dataclass
from typing import Any, Dict, List, Set, Tuple

from app.repositories.knowledge_repository import KnowledgeRepository
from app.schemas.retrieval import RetrievalScope
from app.services.retrieval.base import EntityCandidate, RelationshipCandidate
from app.services.retrieval.scope_resolver import ResolvedScope


@dataclass
class GraphExpansionResult:
    """Contains the resolved entities and relationships compiled during traversal."""
    entities: List[EntityCandidate]
    relationships: List[RelationshipCandidate]


class GraphExpander:
    """
    Traverses the knowledge graph starting from lexical matching seeds (hop_distance=0).
    Performs BFS neighbor resolution up to max_depth, scoping traversal
    to the target finalized version and filtering by relationship types.
    """

    def __init__(self, repo: KnowledgeRepository):
        self.repo = repo

    def expand(
        self,
        lexical_candidates: List[EntityCandidate],
        resolved_scope: ResolvedScope,
        scope_filters: RetrievalScope,
        max_depth: int
    ) -> GraphExpansionResult:
        """
        Expands search candidates via BFS.
        Capped at max_depth (0 <= max_depth <= 3).
        """
        # Depth 0: no expansion, return direct hits
        if max_depth <= 0 or not lexical_candidates:
            # Ensure hop_distance is set to 0 for all lexical hits
            for c in lexical_candidates:
                c.hop_distance = 0
            return GraphExpansionResult(
                entities=lexical_candidates,
                relationships=[]
            )

        # BFS state
        visited_entities: Dict[str, int] = {}  # entity_id -> min_hop_distance
        resolved_entities: Dict[str, Any] = {}  # entity_id -> entity object
        queue: List[Tuple[str, int]] = []  # queue of (entity_id, current_hop)

        # Initialize BFS queue and state with lexical hits
        for cand in lexical_candidates:
            ent_id = cand.entity.id
            visited_entities[ent_id] = 0
            resolved_entities[ent_id] = cand.entity
            queue.append((ent_id, 0))

        collected_relationships: List[RelationshipCandidate] = []
        relationship_keys: Set[Tuple[str, str, str]] = set()

        # BFS loop
        while queue:
            entity_id, current_hop = queue.pop(0)

            # Do not expand neighbors past max_depth
            if current_hop >= max_depth:
                continue

            # Fetch relationship endpoints
            rels = self.repo.get_entity_relationships(resolved_scope.version_id, entity_id)
            all_rels = rels.get("incoming", []) + rels.get("outgoing", [])

            for rel in all_rels:
                # Type constraint: filter relationships by scope
                if scope_filters.relationship_types:
                    if rel.relationship_type not in scope_filters.relationship_types:
                        continue

                # Determine neighbor ID
                if rel.source_entity_id == entity_id:
                    neighbor_id = rel.target_entity_id
                else:
                    neighbor_id = rel.source_entity_id

                new_hop = current_hop + 1

                # Lazy fetch neighbor entity
                if neighbor_id not in resolved_entities:
                    neighbor_obj = self.repo.get_entity(resolved_scope.version_id, neighbor_id)
                    if not neighbor_obj:
                        continue  # Skip dangling reference
                    resolved_entities[neighbor_id] = neighbor_obj

                # Update path minimum hop distance and push to queue
                if neighbor_id not in visited_entities or new_hop < visited_entities[neighbor_id]:
                    visited_entities[neighbor_id] = new_hop
                    queue.append((neighbor_id, new_hop))

                # Collect relationship candidate (deduplicated)
                rel_key = (rel.source_entity_id, rel.target_entity_id, rel.relationship_type)
                if rel_key not in relationship_keys:
                    relationship_keys.add(rel_key)

                    # Lazy fetch source/target entity objects for relationship contract
                    if rel.source_entity_id not in resolved_entities:
                        resolved_entities[rel.source_entity_id] = self.repo.get_entity(
                            resolved_scope.version_id, rel.source_entity_id
                        )
                    if rel.target_entity_id not in resolved_entities:
                        resolved_entities[rel.target_entity_id] = self.repo.get_entity(
                            resolved_scope.version_id, rel.target_entity_id
                        )

                    src_obj = resolved_entities[rel.source_entity_id]
                    tgt_obj = resolved_entities[rel.target_entity_id]

                    if src_obj and tgt_obj:
                        collected_relationships.append(
                            RelationshipCandidate(
                                relationship=rel,
                                source_entity=src_obj,
                                target_entity=tgt_obj,
                                hop_distance=new_hop
                            )
                        )

        # Split results into lexical hits vs neighbor extensions for deterministic sorting
        lexical_hits: List[EntityCandidate] = []
        graph_neighbors: List[EntityCandidate] = []

        for ent_id, hop in visited_entities.items():
            ent_obj = resolved_entities[ent_id]
            lex_cand = next((c for c in lexical_candidates if c.entity.id == ent_id), None)
            if lex_cand:
                lex_cand.hop_distance = 0
                lexical_hits.append(lex_cand)
            else:
                graph_neighbors.append(
                    EntityCandidate(
                        entity=ent_obj,
                        match_score=0.0,
                        match_reason="graph_neighbor",
                        matched_terms=[],
                        hop_distance=hop
                    )
                )

        # Deterministic sorting:
        # Lexical hits: match_score desc, stable_id asc
        lexical_hits.sort(key=lambda c: (-c.match_score, c.entity.stable_id))

        # Neighbors: hop_distance asc, stable_id asc
        graph_neighbors.sort(key=lambda c: (c.hop_distance, c.entity.stable_id))

        # Relationships: hop_distance asc, source stable_id asc, target stable_id asc, relationship_type asc
        collected_relationships.sort(key=lambda r: (
            r.hop_distance,
            r.source_entity.stable_id,
            r.target_entity.stable_id,
            r.relationship.relationship_type
        ))

        return GraphExpansionResult(
            entities=lexical_hits + graph_neighbors,
            relationships=collected_relationships
        )
