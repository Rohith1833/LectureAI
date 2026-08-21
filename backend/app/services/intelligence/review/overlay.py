import hashlib
from typing import List, Dict, Any, Optional, Set, Tuple
from app.schemas.academic import AcademicNode, AcademicEdge, AcademicNodeCategory
from app.schemas.review import ReconciliationStatus, ResolvedGraphResult, NodeReviewState
from app.models.review import AcademicOverride


def calculate_graph_fingerprint(nodes: List[AcademicNode], edges: List[AcademicEdge]) -> str:
    """
    Calculates a deterministic SHA-256 fingerprint for the AcademicGraph.
    Depends purely on the logical state (categories, hierarchy containment, titles, and prerequisite edges).
    """
    # Map child node_id to parent node's anchor_key (from CONTAINS edges)
    child_to_parent_map: Dict[str, str] = {}
    for edge in edges:
        if edge.edge_type == "CONTAINS":
            child_to_parent_map[edge.target_node_id] = edge.source_node_id

    # Map node_id to anchor_key
    node_id_to_anchor = {n.node_id: (n.anchor_key or "") for n in nodes}

    # Serialize nodes
    serialized_nodes = []
    for n in nodes:
        parent_node_id = child_to_parent_map.get(n.node_id)
        parent_anchor = node_id_to_anchor.get(parent_node_id, "") if parent_node_id else ""
        anchor = n.anchor_key or n.node_id
        serialized = f"{anchor}:{n.category.value}:{parent_anchor}:{n.title}"
        serialized_nodes.append(serialized)

    serialized_nodes.sort()

    # Serialize edges (excluding containment which is already captured in parent_anchor)
    serialized_edges = []
    for edge in edges:
        if edge.edge_type != "CONTAINS":
            source_anchor = node_id_to_anchor.get(edge.source_node_id, edge.source_node_id)
            target_anchor = node_id_to_anchor.get(edge.target_node_id, edge.target_node_id)
            serialized_edges.append(f"{source_anchor}->{edge.edge_type}->{target_anchor}")

    serialized_edges.sort()

    content = "\n".join(serialized_nodes) + "\n---\n" + "\n".join(serialized_edges)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class AcademicOverlayService:
    """Compiles base AcademicGraph and manual corrections into a resolved AcademicGraph."""

    @staticmethod
    def detect_cycle(nodes: List[AcademicNode], edges: List[AcademicEdge]) -> bool:
        """Helper to run a DFS detecting cycles on 'CONTAINS' containment hierarchy edges."""
        adj = {n.node_id: [] for n in nodes}
        for edge in edges:
            if edge.edge_type == "CONTAINS":
                # Verify nodes exist before mapping adjacencies
                if edge.source_node_id in adj and edge.target_node_id in adj:
                    adj[edge.source_node_id].append(edge.target_node_id)

        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def dfs(u: str) -> bool:
            visited.add(u)
            rec_stack.add(u)
            for v in adj[u]:
                if v not in visited:
                    if dfs(v):
                        return True
                elif v in rec_stack:
                    return True
            rec_stack.remove(u)
            return False

        for node in nodes:
            if node.node_id not in visited:
                if dfs(node.node_id):
                    return True
        return False

    def compile_resolved_graph(
        self,
        base_nodes: List[AcademicNode],
        base_edges: List[AcademicEdge],
        overrides: List[AcademicOverride]
    ) -> ResolvedGraphResult:
        """
        Applies active overrides on top of the base graph deterministically.
        Treats inputs as read-only.
        """
        # Deep copy to ensure input immutability
        nodes = [n.model_copy(deep=True) for n in base_nodes]
        edges = [e.model_copy(deep=True) for e in base_edges]

        # Calculate base fingerprint
        base_fingerprint = calculate_graph_fingerprint(nodes, edges)

        # Pre-build mappings for fast O(N) access
        def rebuild_lookups():
            node_map = {n.node_id: n for n in nodes}
            anchor_map = {}
            for n in nodes:
                if n.anchor_key:
                    anchor_map.setdefault(n.anchor_key, []).append(n)
            return node_map, anchor_map

        node_map, anchor_map = rebuild_lookups()

        # Sort overrides chronologically: created_at asc, override_id asc
        sorted_overrides = sorted(overrides, key=lambda o: (o.created_at, o.id))

        applied_ids: List[str] = []
        stale_ids: List[str] = []
        conflicted_ids: List[str] = []
        val_errors: List[str] = []
        val_warnings: List[str] = []

        # Conflict check for multiple overrides of same action type on same anchor key
        anchor_actions: Dict[Tuple[str, str], List[AcademicOverride]] = {}
        for o in sorted_overrides:
            if o.action_type != "CREATE_NODE":
                key = (o.target_anchor_key, o.action_type)
                anchor_actions.setdefault(key, []).append(o)

        conflicting_overrides: Set[str] = set()
        for key, o_list in anchor_actions.items():
            if len(o_list) > 1:
                # Check compatibility: if payloads differ, they conflict
                first_payload = o_list[0].payload
                for other in o_list[1:]:
                    if other.payload != first_payload:
                        conflicting_overrides.update(o.id for o in o_list)
                        break

        # Process overrides deterministically
        for o in sorted_overrides:
            if o.id in conflicting_overrides:
                conflicted_ids.append(o.id)
                val_warnings.append(f"Override '{o.id}' was skipped due to logical conflicts on anchor '{o.target_anchor_key}'.")
                continue

            if o.action_type == "CREATE_NODE":
                # Create node doesn't require matching an existing target anchor key
                payload = o.payload
                try:
                    category_val = payload.get("category")
                    if not category_val:
                        raise ValueError("Payload missing category parameter")
                    category = AcademicNodeCategory(category_val)
                    
                    new_node = AcademicNode(
                        node_id=f"an_manual_{o.id}",
                        category=category,
                        title=payload.get("title", "Human Created Node"),
                        target_block_id=payload.get("target_block_id"),
                        anchor_key=payload.get("anchor_key") or f"anc_manual_{o.id}",
                        review_state=NodeReviewState.MODIFIED,
                        metadata={
                            "provenance": "HUMAN_OVERRIDE",
                            "override_ids": [o.id]
                        }
                    )
                    nodes.append(new_node)
                    applied_ids.append(o.id)
                    # Refresh lookup mappings
                    node_map, anchor_map = rebuild_lookups()
                except Exception as ex:
                    val_errors.append(f"CREATE_NODE override '{o.id}' failed: {str(ex)}")
                continue

            # Resolve anchor key
            targets = anchor_map.get(o.target_anchor_key, [])
            if len(targets) == 0:
                stale_ids.append(o.id)
                val_warnings.append(f"Override '{o.id}' marked stale. Target anchor '{o.target_anchor_key}' not found.")
                continue
            elif len(targets) > 1:
                conflicted_ids.append(o.id)
                val_warnings.append(f"Override '{o.id}' marked ambiguous. Target anchor '{o.target_anchor_key}' returned multiple candidates.")
                continue

            target_node = targets[0]

            # Execute explicit validation and overlays
            if o.action_type == "CHANGE_CATEGORY":
                try:
                    new_cat = AcademicNodeCategory(o.payload.get("new_category"))
                    # Preserve original category in metadata
                    if "original_category" not in target_node.metadata:
                        target_node.metadata["original_category"] = target_node.category.value
                    
                    target_node.category = new_cat
                    target_node.review_state = NodeReviewState.MODIFIED
                    target_node.metadata.setdefault("override_ids", []).append(o.id)
                    applied_ids.append(o.id)
                except Exception as ex:
                    val_errors.append(f"CHANGE_CATEGORY override '{o.id}' failed: {str(ex)}")

            elif o.action_type == "ACCEPT_NODE":
                target_node.review_state = NodeReviewState.ACCEPTED
                target_node.metadata.setdefault("override_ids", []).append(o.id)
                applied_ids.append(o.id)

            elif o.action_type == "RENAME_TITLE":
                new_title = o.payload.get("new_title")
                if not new_title or not isinstance(new_title, str) or not new_title.strip():
                    val_errors.append(f"RENAME_TITLE override '{o.id}' failed: Title cannot be empty.")
                else:
                    if "original_title" not in target_node.metadata:
                        target_node.metadata["original_title"] = target_node.title
                    
                    target_node.title = new_title.strip()
                    target_node.review_state = NodeReviewState.MODIFIED
                    target_node.metadata.setdefault("override_ids", []).append(o.id)
                    applied_ids.append(o.id)

            elif o.action_type == "REPARENT_NODE":
                new_parent_id = o.payload.get("new_parent_id")
                # Look up parent by anchor if parent ID not provided
                if not new_parent_id and o.payload.get("new_parent_anchor"):
                    candidates = anchor_map.get(o.payload.get("new_parent_anchor"), [])
                    if len(candidates) == 1:
                        new_parent_id = candidates[0].node_id

                if not new_parent_id or new_parent_id not in node_map:
                    val_errors.append(f"REPARENT_NODE override '{o.id}' failed: New parent ID '{new_parent_id}' not found.")
                elif new_parent_id == target_node.node_id:
                    val_errors.append(f"REPARENT_NODE override '{o.id}' failed: Self-referencing parent is invalid.")
                else:
                    # Find and update existing CONTAINS edge, or insert a new one
                    reparented = False
                    # Keep track of old parent for metadata provenance
                    old_parent_id = None
                    for edge in edges:
                        if edge.edge_type == "CONTAINS" and edge.target_node_id == target_node.node_id:
                            old_parent_id = edge.source_node_id
                            edge.source_node_id = new_parent_id
                            reparented = True
                            break
                    if not reparented:
                        edges.append(AcademicEdge(
                            source_node_id=new_parent_id,
                            target_node_id=target_node.node_id,
                            edge_type="CONTAINS",
                            confidence=1.0
                        ))

                    # Cycle check validation
                    if self.detect_cycle(nodes, edges):
                        # Revert edge shift
                        if reparented:
                            for edge in edges:
                                if edge.edge_type == "CONTAINS" and edge.target_node_id == target_node.node_id:
                                    edge.source_node_id = old_parent_id
                                    break
                        else:
                            edges.pop()
                        val_errors.append(f"REPARENT_NODE override '{o.id}' failed: Containment cycle detected.")
                    else:
                        if old_parent_id and "original_parent_id" not in target_node.metadata:
                            target_node.metadata["original_parent_id"] = old_parent_id
                        target_node.review_state = NodeReviewState.MODIFIED
                        target_node.metadata.setdefault("override_ids", []).append(o.id)
                        applied_ids.append(o.id)

            elif o.action_type == "DELETE_NODE":
                target_node.review_state = NodeReviewState.REJECTED
                target_node.metadata.setdefault("override_ids", []).append(o.id)
                applied_ids.append(o.id)

            elif o.action_type == "UPDATE_EDGE":
                payload = o.payload
                src = payload.get("source_node_id")
                tgt = payload.get("target_node_id")
                edge_type = payload.get("edge_type", "PREREQUISITE_OF")
                conf = payload.get("confidence", 1.0)

                # Resolve source via anchor if node_id not direct
                if not src and payload.get("source_anchor"):
                    candidates = anchor_map.get(payload.get("source_anchor"), [])
                    if len(candidates) == 1:
                        src = candidates[0].node_id

                # Resolve target via anchor if node_id not direct
                if not tgt and payload.get("target_anchor"):
                    candidates = anchor_map.get(payload.get("target_anchor"), [])
                    if len(candidates) == 1:
                        tgt = candidates[0].node_id

                if not src or not tgt:
                    val_errors.append(f"UPDATE_EDGE override '{o.id}' failed: Source and target must be defined (via ID or stable anchor).")
                elif src not in node_map or tgt not in node_map:
                    val_errors.append(f"UPDATE_EDGE override '{o.id}' failed: Edge endpoints not found.")
                elif src == tgt:
                    val_errors.append(f"UPDATE_EDGE override '{o.id}' failed: Self-referencing relationships are invalid.")
                else:
                    # Update existing edge or append new
                    updated = False
                    for edge in edges:
                        if edge.source_node_id == src and edge.target_node_id == tgt and edge.edge_type == edge_type:
                            edge.confidence = conf
                            updated = True
                            break
                    if not updated:
                        edges.append(AcademicEdge(
                            source_node_id=src,
                            target_node_id=tgt,
                            edge_type=edge_type,
                            confidence=conf
                        ))
                    applied_ids.append(o.id)

        # 3. Post-compilation: Filter out deleted/rejected nodes and their connected edges
        rejected_node_ids = {n.node_id for n in nodes if n.review_state == NodeReviewState.REJECTED}
        resolved_nodes = [n for n in nodes if n.review_state != NodeReviewState.REJECTED]
        resolved_edges = [
            e for e in edges
            if e.source_node_id not in rejected_node_ids and e.target_node_id not in rejected_node_ids
        ]

        # Cycle check validation on resolved graph
        if self.detect_cycle(resolved_nodes, resolved_edges):
            val_errors.append("Invalid graph: Containment cycle exists in the resolved graph structure.")

        # Calculate resolved fingerprint
        resolved_fingerprint = calculate_graph_fingerprint(resolved_nodes, resolved_edges)

        # Resolve status verdict
        if val_errors:
            status = ReconciliationStatus.INVALID_GRAPH
        elif conflicted_ids:
            status = ReconciliationStatus.CONFLICTS
        elif stale_ids:
            status = ReconciliationStatus.STALE_OVERRIDES
        else:
            status = ReconciliationStatus.CLEAN

        return ResolvedGraphResult(
            nodes=resolved_nodes,
            edges=resolved_edges,
            base_graph_fingerprint=base_fingerprint,
            resolved_graph_fingerprint=resolved_fingerprint,
            applied_override_ids=applied_ids,
            stale_override_ids=stale_ids,
            conflicted_override_ids=conflicted_ids,
            validation_errors=val_errors,
            validation_warnings=val_warnings,
            reconciliation_status=status
        )


ResolvedGraphResult.model_rebuild()

