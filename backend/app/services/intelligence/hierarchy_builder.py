import time
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

from app.schemas.document import BlockSchema, BlockType
from app.services.intelligence.base import BaseIntelligenceModule, ModuleMetadata
from app.services.intelligence.context import IntelligenceContext
from app.services.intelligence.annotations import ConfidenceScore, HierarchyAnnotation
from app.services.intelligence.features import FeatureAnnotation
from app.services.intelligence.graph import (
    ReadingEdgeType,
    ReadingGraphEdge,
    DocumentReadingGraphAnnotation,
)
from app.services.intelligence.events import (
    HierarchyConstructionStarted,
    HierarchyNodeCreated,
    HierarchyCompleted,
)


class HierarchyBuilderModule(BaseIntelligenceModule):
    """Constructs parent-child hierarchy trees, logical section boundaries, and document graphs."""

    def __init__(self):
        self._metadata = ModuleMetadata(
            name="HIERARCHY_BUILDER_MODULE",
            version="1.0.0",
            author="LectureAI Core",
            stage="hierarchy_construction",
            priority=100,
            dependencies=[
                "FEATURE_EXTRACTION_MODULE",
                "HEADING_DETECTION_MODULE",
                "LIST_QUOTE_NOTE_DETECTION_MODULE",
                "TABLE_CAPTION_DETECTION_MODULE",
                "CODE_FORMULA_DETECTION_MODULE",
                "READING_ORDER_INTELLIGENCE_MODULE",
            ],
            enabled=True,
        )

    @property
    def metadata(self) -> ModuleMetadata:
        return self._metadata

    def initialize(self, config: dict) -> None:
        pass

    def execute(self, context: IntelligenceContext) -> None:
        doc = context.document
        if not doc or not doc.blocks:
            context.event_publisher.publish(HierarchyCompleted(upload_id=doc.upload_id if doc else "unknown", node_count=0))
            return

        # Publish event: HierarchyConstructionStarted
        context.event_publisher.publish(HierarchyConstructionStarted(upload_id=doc.upload_id))

        # Fetch feature annotations
        feature_annos = context.annotation_store.find_by_type(FeatureAnnotation)
        anno_map = {a.target_id: a for a in feature_annos}

        # 1. Traversal Stack Setup
        stack: List[BlockSchema] = []
        parent_to_children_map: Dict[str, List[BlockSchema]] = defaultdict(list)
        block_parent_map: Dict[str, str] = {}
        caption_associations: List[Tuple[str, str]] = []  # List of (caption_id, target_id)

        # 2. Iterate in reading order to resolve parent-child
        for idx, block in enumerate(doc.blocks):
            block_id = block.block_id
            b_type = block.block_type

            # Check indentation from features
            margin = 50.0
            if block_id in anno_map:
                margin = anno_map[block_id].features.geometry.margin_left

            # A. CAPTION special handling
            if b_type == BlockType.CAPTION:
                caption_target = None
                # Check preceding block
                if idx > 0:
                    prev_b = doc.blocks[idx - 1]
                    if prev_b.block_type in (BlockType.TABLE, BlockType.EQUATION, BlockType.CODE):
                        caption_target = prev_b
                # Check following block
                if not caption_target and idx < len(doc.blocks) - 1:
                    next_b = doc.blocks[idx + 1]
                    if next_b.block_type in (BlockType.TABLE, BlockType.EQUATION, BlockType.CODE):
                        caption_target = next_b

                if caption_target:
                    caption_associations.append((block_id, caption_target.block_id))
                    block_parent_map[block_id] = caption_target.block_id
                    parent_to_children_map[caption_target.block_id].append(block)
                    block.parent_block_id = caption_target.block_id
                    
                    context.event_publisher.publish(
                        HierarchyNodeCreated(
                            upload_id=doc.upload_id,
                            block_id=block_id,
                            parent_id=caption_target.block_id,
                            relation="caption_association",
                        )
                    )
                    continue

            # B. Stack-based resolution rules
            if b_type == BlockType.HEADING:
                # Pop non-headings, and headings of equal or deeper level
                while stack:
                    top = stack[-1]
                    if top.block_type != BlockType.HEADING:
                        stack.pop()
                    elif top.heading_level is not None and block.heading_level is not None and top.heading_level >= block.heading_level:
                        stack.pop()
                    else:
                        break
            elif b_type == BlockType.LIST:
                # Manage nested lists by margin indents
                while stack:
                    top = stack[-1]
                    if top.block_type == BlockType.LIST:
                        top_margin = 50.0
                        if top.block_id in anno_map:
                            top_margin = anno_map[top.block_id].features.geometry.margin_left
                        
                        if margin > top_margin + 10.0:
                            # Nested list
                            break
                        else:
                            # Sibling list item
                            stack.pop()
                    elif top.block_type != BlockType.HEADING:
                        stack.pop()
                    else:
                        break
            else:
                # Standard content block: Pop non-headings, unless inside a list item
                while stack:
                    top = stack[-1]
                    if top.block_type == BlockType.LIST:
                        top_margin = 50.0
                        if top.block_id in anno_map:
                            top_margin = anno_map[top.block_id].features.geometry.margin_left
                        if margin < top_margin - 5.0:
                            stack.pop()
                        else:
                            break
                    elif top.block_type != BlockType.HEADING:
                        stack.pop()
                    else:
                        break

            # C. Assign parent
            if stack:
                parent = stack[-1]
                block_parent_map[block_id] = parent.block_id
                parent_to_children_map[parent.block_id].append(block)
                block.parent_block_id = parent.block_id
                
                context.event_publisher.publish(
                    HierarchyNodeCreated(
                        upload_id=doc.upload_id,
                        block_id=block_id,
                        parent_id=parent.block_id,
                        relation="parent_child",
                    )
                )
            else:
                block.parent_block_id = None

            # Push headings and list containers to stack
            if b_type in (BlockType.HEADING, BlockType.LIST):
                stack.append(block)

        # 3. Post-Order Tree Index and Size Computations
        tree_idx = 0
        node_depths: Dict[str, int] = {}
        node_chapter_ids: Dict[str, str] = {}
        node_section_ids: Dict[str, str] = {}
        subtree_sizes: Dict[str, int] = {}
        section_boundaries: Dict[str, Dict[str, Any]] = {}

        # DFS traversal function to calculate boundaries and subtree metrics
        def visit_node(node_id: str, depth: int, active_chapter: Optional[str], active_section: Optional[str]) -> Tuple[int, str]:
            nonlocal tree_idx
            current_idx = tree_idx
            tree_idx += 1

            block_obj = next((b for b in doc.blocks if b.block_id == node_id), None)
            if not block_obj:
                return 0, node_id

            # Inherit active chapters and sections
            if block_obj.block_type == BlockType.HEADING:
                active_section = node_id
                if block_obj.heading_level == 1:
                    active_chapter = node_id

            node_depths[node_id] = depth
            if active_chapter:
                node_chapter_ids[node_id] = active_chapter
            if active_section:
                node_section_ids[node_id] = active_section

            # Recursively visit children
            child_count = 0
            first_desc = None
            last_desc = node_id
            children = parent_to_children_map.get(node_id, [])

            for c in children:
                if not first_desc:
                    first_desc = c.block_id
                sub_size, sub_last = visit_node(c.block_id, depth + 1, active_chapter, active_section)
                child_count += sub_size
                last_desc = sub_last

            total_size = 1 + child_count
            subtree_sizes[node_id] = total_size

            # Save section boundaries
            if block_obj.block_type == BlockType.HEADING:
                section_boundaries[node_id] = {
                    "first_descendant": first_desc,
                    "last_descendant": last_desc,
                    "subtree_size": total_size,
                }

            return total_size, last_desc

        # Run boundary calculators for root headings
        root_blocks = [b for b in doc.blocks if b.parent_block_id is None]
        for root in root_blocks:
            visit_node(root.block_id, depth=0, active_chapter=None, active_section=None)

        # 4. Write Hierarchy Annotations and Reading Graph Edges
        graph_edges: List[ReadingGraphEdge] = []
        graph_nodes: List[str] = [b.block_id for b in doc.blocks]

        for block in doc.blocks:
            b_id = block.block_id
            parent_id = block.parent_block_id
            children = parent_to_children_map.get(b_id, [])
            child_ids = [c.block_id for c in children]

            # Generate sibling lists
            siblings = []
            if parent_id:
                siblings = [c.block_id for c in parent_to_children_map[parent_id] if c.block_id != b_id]

            # Hierarchy Metadata Dictionary
            meta = {
                "depth": node_depths.get(b_id, 0),
                "section_id": node_section_ids.get(b_id),
                "chapter_id": node_chapter_ids.get(b_id),
                "subtree_size": subtree_sizes.get(b_id, 1),
                "sibling_ids": siblings,
            }

            # Check if section boundaries are defined
            if b_id in section_boundaries:
                meta.update(section_boundaries[b_id])

            # Write standard HierarchyAnnotation
            conf_val = 0.90
            anno = HierarchyAnnotation(
                annotation_id=f"h_{b_id}_{int(time.time())}",
                target_id=b_id,
                provenance=self.metadata.name,
                confidence=ConfidenceScore(
                    score=conf_val,
                    contributors={"stack_traversal": conf_val},
                    method="stack_structural_hierarchy",
                ),
                parent_id=parent_id,
                child_ids=child_ids,
                relation_type="heading_hierarchy" if block.block_type == BlockType.HEADING else "parent_child_containment",
                metadata=meta,
            )
            context.annotation_store.add(anno)

            # Build Reading Graph Edges
            if parent_id:
                graph_edges.append(
                    ReadingGraphEdge(
                        source_id=parent_id,
                        target_id=b_id,
                        edge_type=ReadingEdgeType.PARENT_CHILD,
                        confidence=conf_val,
                    )
                )

            # Sibling Edges
            children_objs = parent_to_children_map.get(b_id, [])
            for c_idx in range(len(children_objs) - 1):
                graph_edges.append(
                    ReadingGraphEdge(
                        source_id=children_objs[c_idx].block_id,
                        target_id=children_objs[c_idx + 1].block_id,
                        edge_type=ReadingEdgeType.SIBLING,
                        confidence=0.95,
                    )
                )

            # Reading Flow Edges
            if block.next_block_id:
                graph_edges.append(
                    ReadingGraphEdge(
                        source_id=b_id,
                        target_id=block.next_block_id,
                        edge_type=ReadingEdgeType.READING_FLOW,
                        confidence=0.99,
                    )
                )

        # Append caption associations to graph
        for cap_id, target_id in caption_associations:
            graph_edges.append(
                ReadingGraphEdge(
                    source_id=target_id,
                    target_id=cap_id,
                    edge_type=ReadingEdgeType.CAPTION_ASSOCIATION,
                    confidence=0.95,
                )
            )

        # Write DocumentReadingGraphAnnotation
        graph_anno = DocumentReadingGraphAnnotation(
            annotation_id=f"dg_{doc.upload_id}_{int(time.time())}",
            target_id=doc.upload_id,
            provenance=self.metadata.name,
            confidence=ConfidenceScore(
                score=0.98,
                contributors={"graph_links": 0.98},
                method="flow_graph_resolution",
            ),
            nodes=graph_nodes,
            edges=graph_edges,
        )
        context.annotation_store.add(graph_anno)

        # Publish event: HierarchyCompleted
        context.event_publisher.publish(
            HierarchyCompleted(
                upload_id=doc.upload_id,
                node_count=len(doc.blocks)
            )
        )
