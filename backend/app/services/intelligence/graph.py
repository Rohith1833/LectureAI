import time
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from app.services.intelligence.annotations import BaseAnnotation


class ReadingEdgeType(str, Enum):
    PARENT_CHILD = "PARENT_CHILD"
    SIBLING = "SIBLING"
    CONTAINS = "CONTAINS"
    READING_FLOW = "READING_FLOW"
    NEXT = "NEXT"
    PREV = "PREV"
    CAPTION_ASSOCIATION = "CAPTION_ASSOCIATION"


class ReadingGraphEdge(BaseModel):
    source_id: str = Field(..., description="ID of source layout block")
    target_id: str = Field(..., description="ID of target layout block")
    edge_type: ReadingEdgeType
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentReadingGraphAnnotation(BaseAnnotation):
    """Document-wide reading graph annotation representing logical hierarchies and flow order."""
    nodes: List[str] = Field(..., description="List of all block IDs in sequence")
    edges: List[ReadingGraphEdge] = Field(default_factory=list)


class DocumentGraph:
    """Lightweight traversal wrapper providing simple query operations over hierarchical structures."""

    def __init__(self, document: Any, graph_annotation: DocumentReadingGraphAnnotation):
        self.document = document
        self.graph = graph_annotation
        self.blocks_map = {b.block_id: b for b in document.blocks}
        
        # Build maps for instant O(1) edge lookup
        self.outgoing: Dict[str, List[ReadingGraphEdge]] = {}
        self.incoming: Dict[str, List[ReadingGraphEdge]] = {}
        for edge in graph_annotation.edges:
            self.outgoing.setdefault(edge.source_id, []).append(edge)
            self.incoming.setdefault(edge.target_id, []).append(edge)

    def get_parent(self, block_id: str) -> Optional[Any]:
        """Retrieve the hierarchical parent node ID."""
        for edge in self.incoming.get(block_id, []):
            if edge.edge_type == ReadingEdgeType.PARENT_CHILD:
                return self.blocks_map.get(edge.source_id)
        return None

    def get_children(self, block_id: str) -> List[Any]:
        """Retrieve immediate hierarchical child nodes."""
        children = []
        for edge in self.outgoing.get(block_id, []):
            if edge.edge_type == ReadingEdgeType.PARENT_CHILD:
                child = self.blocks_map.get(edge.target_id)
                if child:
                    children.append(child)
        return children

    def get_next(self, block_id: str) -> Optional[Any]:
        """Retrieve the next node in the reading flow sequence."""
        for edge in self.outgoing.get(block_id, []):
            if edge.edge_type in (ReadingEdgeType.READING_FLOW, ReadingEdgeType.NEXT):
                return self.blocks_map.get(edge.target_id)
        return None

    def get_previous(self, block_id: str) -> Optional[Any]:
        """Retrieve the previous node in the reading flow sequence."""
        for edge in self.incoming.get(block_id, []):
            if edge.edge_type in (ReadingEdgeType.READING_FLOW, ReadingEdgeType.PREV):
                return self.blocks_map.get(edge.source_id)
        return None

    def get_ancestors(self, block_id: str) -> List[Any]:
        """Traverse upwards to retrieve all active parent headings up to the document root."""
        ancestors = []
        current = self.get_parent(block_id)
        while current:
            ancestors.append(current)
            current = self.get_parent(current.block_id)
        return ancestors

    def get_descendants(self, block_id: str) -> List[Any]:
        """Recursively scan the subtree to retrieve all children, grandchildren, etc."""
        descendants = []
        queue = self.get_children(block_id)
        while queue:
            node = queue.pop(0)
            descendants.append(node)
            queue.extend(self.get_children(node.block_id))
        return descendants

    def get_section(self, block_id: str) -> Optional[Any]:
        """Identify the closest containing HEADING section node (or self if heading)."""
        current_block = self.blocks_map.get(block_id)
        if not current_block:
            return None
        if current_block.block_type == "HEADING":
            return current_block
        ancestors = self.get_ancestors(block_id)
        for anc in ancestors:
            if anc.block_type == "HEADING":
                return anc
        return None

    def get_document_path(self, block_id: str) -> List[str]:
        """Generate a breadcrumb list of string titles representing the path from root to current node."""
        ancestors = self.get_ancestors(block_id)
        path_nodes = reversed(ancestors)
        return [node.text for node in path_nodes if hasattr(node, 'text') and node.text]
