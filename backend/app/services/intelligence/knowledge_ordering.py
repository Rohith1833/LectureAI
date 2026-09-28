"""
Knowledge ordering and selectable container resolution module.

Provides:
- Lexicographical canonical source position resolution: min((page_number, reading_order)).
- Graph-based descendant position resolution for containers without direct blocks.
- Deterministic entity sorting using canonical positions, snapshot indices, and stable IDs.
- Graph-based identification of top-level selectable containers (Units vs Chapters vs Review Required).
"""

from typing import List, Dict, Tuple, Optional, Any, Set, Sequence
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict
from sqlalchemy.orm import Session

from app.models.knowledge import KnowledgeEntity, KnowledgeRelationship


SourcePosition = Tuple[int, int]  # (page_number, reading_order)


class SelectableContainerMode(str, Enum):
    UNITS = "UNITS"
    CHAPTERS = "CHAPTERS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(frozen=True)
class SelectableContainersResult:
    mode: SelectableContainerMode
    containers: List[KnowledgeEntity]
    container_type: Optional[str]  # "UNIT", "CHAPTER", or None
    message: str


def compute_canonical_source_position(
    linked_block_positions: List[Tuple[Optional[int], Optional[int]]]
) -> Optional[SourcePosition]:
    """
    Computes the canonical source position from a list of (page_number, reading_order) tuples.
    Preserves valid zero values (page 0 or reading_order 0).
    Uses the lexicographically earliest actual tuple; never computes min page and min reading order independently.
    """
    valid_tuples = [
        (p, ro)
        for p, ro in linked_block_positions
        if p is not None and ro is not None
    ]
    if not valid_tuples:
        return None
    return min(valid_tuples)


def resolve_node_source_positions(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    doc_blocks: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """
    Resolves canonical source positions for all nodes in an academic graph snapshot.
    
    Rules:
    1. Direct position: if node has valid target_block_id in doc_blocks with page_number and reading_order,
       uses (block.page_number, block.reading_order) with origin='DIRECT'.
    2. Descendant-derived: if node has no direct position, searches all descendants reachable via CONTAINS edges.
       Uses min((descendant_page, descendant_reading_order)) with origin='DESCENDANT_DERIVED'.
    3. Fallback: if node has no direct position and no descendants with positions,
       uses None with origin='FALLBACK'.
    
    Returns:
        Dict mapping node_id -> {
            "canonical_source_position": [page, ro] or None,
            "source_position_origin": "DIRECT" | "DESCENDANT_DERIVED" | "FALLBACK",
            "snapshot_index": int,
            "source_position_descendant_id": str or None
        }
    """
    # 1. Map direct positions
    direct_positions: Dict[str, Optional[SourcePosition]] = {}
    for idx, node in enumerate(nodes):
        node_id = node.get("node_id", f"node_{idx}")
        target_block_id = node.get("target_block_id")
        block = doc_blocks.get(target_block_id) if target_block_id else None
        
        if block and block.page_number is not None and block.reading_order is not None:
            direct_positions[node_id] = (int(block.page_number), int(block.reading_order))
        else:
            direct_positions[node_id] = None

    # 2. Build containment adjacency list: parent -> children
    children_map: Dict[str, List[str]] = defaultdict(list)
    for edge in edges:
        if edge.get("edge_type") == "CONTAINS":
            src = edge.get("source_node_id")
            tgt = edge.get("target_node_id")
            if src and tgt:
                children_map[src].append(tgt)

    # 3. Resolve positions for all nodes
    resolved: Dict[str, Dict[str, Any]] = {}
    for idx, node in enumerate(nodes):
        node_id = node.get("node_id", f"node_{idx}")
        direct_pos = direct_positions.get(node_id)
        
        if direct_pos is not None:
            resolved[node_id] = {
                "canonical_source_position": [direct_pos[0], direct_pos[1]],
                "source_position_origin": "DIRECT",
                "snapshot_index": idx,
                "source_position_descendant_id": None,
            }
        else:
            # BFS to find all reachable descendants
            visited: Set[str] = set()
            queue = list(children_map.get(node_id, []))
            candidate_positions: List[Tuple[SourcePosition, str]] = []
            
            while queue:
                curr = queue.pop(0)
                if curr in visited:
                    continue
                visited.add(curr)
                
                pos = direct_positions.get(curr)
                if pos is not None:
                    candidate_positions.append((pos, curr))
                
                for child in children_map.get(curr, []):
                    if child not in visited:
                        queue.append(child)
            
            if candidate_positions:
                best_pos, best_descendant = min(candidate_positions, key=lambda x: x[0])
                resolved[node_id] = {
                    "canonical_source_position": [best_pos[0], best_pos[1]],
                    "source_position_origin": "DESCENDANT_DERIVED",
                    "snapshot_index": idx,
                    "source_position_descendant_id": best_descendant,
                }
            else:
                resolved[node_id] = {
                    "canonical_source_position": None,
                    "source_position_origin": "FALLBACK",
                    "snapshot_index": idx,
                    "source_position_descendant_id": None,
                }

    return resolved


def entity_sort_key(entity: KnowledgeEntity) -> Tuple[int, int, int, int, str, str]:
    """
    Deterministic sort key for a KnowledgeEntity:
    1. Position presence flag (0 if positioned, 1 if unpositioned).
    2. Page number (or 999999999 if unpositioned).
    3. Reading order (or 999999999 if unpositioned).
    4. Snapshot index (from metadata, or 999999999).
    5. Stable ID (lexicographical string tie-break).
    6. Internal entity UUID (final deterministic tie-break).
    """
    raw_meta = getattr(entity, "metadata_json", None)
    if isinstance(raw_meta, dict):
        meta = raw_meta
    else:
        candidate = getattr(entity, "metadata", None)
        meta = candidate if isinstance(candidate, dict) else {}
    pos = meta.get("canonical_source_position")
    
    if pos is not None and isinstance(pos, (list, tuple)) and len(pos) >= 2:
        p, ro = pos[0], pos[1]
        has_pos = 0
    else:
        p, ro = 999999999, 999999999
        has_pos = 1
        
    snap_idx = meta.get("snapshot_index", 999999999)
    stable_id = entity.stable_id or ""
    entity_id = entity.id or ""
    
    return (has_pos, p, ro, snap_idx, stable_id, entity_id)


def sort_entities_by_source_order(entities: List[KnowledgeEntity]) -> List[KnowledgeEntity]:
    """
    Sorts a list of knowledge entities deterministically by canonical source order.
    Guarantees deterministic ordering regardless of insertion order, database return order, or random UUIDs.
    """
    return sorted(entities, key=entity_sort_key)


def get_selectable_containers(
    db: Session,
    knowledge_version_id: str
) -> SelectableContainersResult:
    """
    Identifies ordered, selectable academic containers for a finalized knowledge version.
    
    Rules:
    1. If entities of type 'UNIT' exist:
       Identifies top-level UNITs (those not contained in another UNIT) via the containment graph.
       Returns mode='UNITS'.
    2. If no 'UNIT' entities exist, but 'CHAPTER' entities exist:
       Identifies top-level CHAPTERs (those not contained in another CHAPTER or container) via containment graph.
       Returns mode='CHAPTERS'.
    3. If neither top-level units nor top-level chapters exist:
       Returns mode='REVIEW_REQUIRED' with containers=[] (does not manufacture units).
       
    Containers are always returned in deterministic canonical source order.
    """
    # Fetch all entities in this knowledge version
    entities = (
        db.query(KnowledgeEntity)
        .filter(KnowledgeEntity.knowledge_version_id == knowledge_version_id)
        .all()
    )
    if not entities:
        return SelectableContainersResult(
            mode=SelectableContainerMode.REVIEW_REQUIRED,
            containers=[],
            container_type=None,
            message="Knowledge version contains no entities."
        )

    entity_map = {e.id: e for e in entities}

    # Fetch CONTAINS relationships for this version
    relationships = (
        db.query(KnowledgeRelationship)
        .filter(
            KnowledgeRelationship.knowledge_version_id == knowledge_version_id,
            KnowledgeRelationship.relationship_type == "CONTAINS"
        )
        .all()
    )

    child_to_parents: Dict[str, Set[str]] = defaultdict(set)
    for rel in relationships:
        r_type = rel.relationship_type.value if hasattr(rel.relationship_type, "value") else str(rel.relationship_type)
        if r_type == "CONTAINS":
            if rel.source_entity_id in entity_map and rel.target_entity_id in entity_map:
                child_to_parents[rel.target_entity_id].add(rel.source_entity_id)

    def get_ancestors(node_id: str) -> Tuple[Set[str], bool]:
        """Returns all ancestor entity IDs and whether a cycle was detected."""
        ancestors: Set[str] = set()
        visited: Set[str] = set()
        queue = list(child_to_parents.get(node_id, set()))
        has_cycle = False
        
        while queue:
            curr = queue.pop(0)
            if curr == node_id:
                has_cycle = True
            if curr in visited:
                continue
            visited.add(curr)
            ancestors.add(curr)
            for p in child_to_parents.get(curr, set()):
                if p not in visited:
                    queue.append(p)
        return ancestors, has_cycle

    def get_entity_type_str(entity_obj: Any) -> str:
        etype = getattr(entity_obj, "entity_type", "")
        return etype.value if hasattr(etype, "value") else str(etype)

    # 1. Check for UNIT containers
    units = [e for e in entities if get_entity_type_str(e) == "UNIT"]
    if units:
        # Top-level units: not contained in another UNIT directly or indirectly
        top_units = []
        for u in units:
            ancestors, has_cycle = get_ancestors(u.id)
            has_unit_ancestor = any(
                entity_map.get(aid) and get_entity_type_str(entity_map[aid]) == "UNIT"
                for aid in ancestors
            )
            if not has_unit_ancestor and not has_cycle:
                top_units.append(u)

        if top_units:
            ordered_units = sort_entities_by_source_order(top_units)
            return SelectableContainersResult(
                mode=SelectableContainerMode.UNITS,
                containers=ordered_units,
                container_type="UNIT",
                message=f"Found {len(ordered_units)} academic units."
            )

    # 2. Check for CHAPTER containers (Chapters mode)
    chapters = [e for e in entities if get_entity_type_str(e) == "CHAPTER"]
    if chapters:
        # Top-level chapters: not contained in another CHAPTER or a UNIT directly or indirectly
        top_chapters = []
        for c in chapters:
            ancestors, has_cycle = get_ancestors(c.id)
            has_blocking_ancestor = any(
                entity_map.get(aid) and get_entity_type_str(entity_map[aid]) in ("CHAPTER", "UNIT")
                for aid in ancestors
            )
            if not has_blocking_ancestor and not has_cycle:
                top_chapters.append(c)

        if top_chapters:
            ordered_chapters = sort_entities_by_source_order(top_chapters)
            return SelectableContainersResult(
                mode=SelectableContainerMode.CHAPTERS,
                containers=ordered_chapters,
                container_type="CHAPTER",
                message=f"No units detected; operating in Chapters mode with {len(ordered_chapters)} top-level chapters."
            )

    # 3. Neither found or malformed cycle -> Review Required
    return SelectableContainersResult(
        mode=SelectableContainerMode.REVIEW_REQUIRED,
        containers=[],
        container_type=None,
        message="No selectable academic containers (units or chapters) found in knowledge version. Academic review required."
    )


def get_container_descendants(
    container_id: str,
    relationships: Sequence[Any]
) -> Set[str]:
    """
    Computes the set of all descendant entity IDs reachable via outgoing CONTAINS edges from container_id.
    Handles arbitrary depth (UNIT -> CHAPTER -> SECTION -> TOPIC -> CONCEPT) with cycle termination.
    """
    children_map: Dict[str, List[str]] = defaultdict(list)
    for rel in relationships:
        r_type = getattr(rel, "relationship_type", None)
        r_type_str = r_type.value if hasattr(r_type, "value") else str(r_type)
        if r_type_str == "CONTAINS":
            src = getattr(rel, "source_entity_id", None)
            tgt = getattr(rel, "target_entity_id", None)
            if src and tgt:
                children_map[src].append(tgt)

    descendants: Set[str] = set()
    visited: Set[str] = {container_id}
    queue = list(children_map.get(container_id, []))

    while queue:
        curr = queue.pop(0)
        if curr in visited:
            continue
        visited.add(curr)
        descendants.add(curr)
        for child in children_map.get(curr, []):
            if child not in visited:
                queue.append(child)

    return descendants

