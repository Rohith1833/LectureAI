from typing import Dict, List, Any
from app.schemas.academic import AcademicNode, AcademicEdge, AcademicNodeCategory
from app.services.intelligence.base import BaseIntelligenceModule, ModuleMetadata
from app.services.intelligence.context import IntelligenceContext
from app.services.intelligence.annotations import AcademicAnnotation
from app.services.intelligence.graph import DocumentGraph


class AcademicGraphBuilderModule(BaseIntelligenceModule):
    """Assembles AcademicAnnotations into a decoupled logical hierarchy and prerequisite mapping graph."""

    def __init__(self):
        self._metadata = ModuleMetadata(
            name="ACADEMIC_GRAPH_BUILDER_MODULE",
            version="1.0.0",
            author="LectureAI Core",
            stage="academic_graph_construction",
            priority=145,
            dependencies=[
                "CURRICULUM_CLASSIFICATION_MODULE",
                "EXPOSITORY_CLASSIFICATION_MODULE",
                "PEDAGOGICAL_CLASSIFICATION_MODULE",
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
        if not doc:
            return

        # Fetch all AcademicAnnotations
        annos = context.annotation_store.find_by_type(AcademicAnnotation)
        if not annos:
            context.shared_cache["academic_graph"] = {"nodes": [], "edges": []}
            return

        # Fetch DocumentReadingGraphAnnotation
        from app.services.intelligence.graph import DocumentReadingGraphAnnotation
        from app.services.intelligence.annotations import ConfidenceScore
        
        graphs = context.annotation_store.find_by_type(DocumentReadingGraphAnnotation)
        graph_anno = graphs[0] if graphs else None
        
        if not graph_anno:
            graph_anno = DocumentReadingGraphAnnotation(
                annotation_id="temp_g",
                target_id=doc.upload_id,
                provenance="temp",
                confidence=ConfidenceScore(score=1.0),
                nodes=[b.block_id for b in doc.blocks],
                edges=[]
            )

        # Instantiate navigation facade
        doc_graph = DocumentGraph(doc, graph_anno)

        nodes: List[AcademicNode] = []
        edges: List[AcademicEdge] = []

        # 1. Resolve stable Contextual Anchor Keys
        from app.services.intelligence.review.identity import resolve_anchor_keys_for_nodes
        
        nodes_data = []
        for anno in annos:
            category = AcademicNodeCategory(anno.academic_type)
            target_block = next((b for b in doc.blocks if b.block_id == anno.target_id), None)
            text = target_block.text if target_block else ""
            nodes_data.append((anno.target_id, text, category))

        anchor_map, diagnostics = resolve_anchor_keys_for_nodes(doc.upload_id, nodes_data, doc_graph)

        # Log collision diagnostics
        if diagnostics:
            context.shared_cache["academic_graph_collisions"] = diagnostics
            for diag in diagnostics:
                context.diagnostics.append({
                    "module": self.metadata.name,
                    "warning": f"[ANCHOR_KEY_COLLISION_DETECTED] Anchor key '{diag['anchor_key']}' collided between blocks {[c['block_id'] for c in diag['conflicts']]}."
                })

        # 2. Create AcademicNodes mapping target block references
        # Map block_id to academic_node_id
        block_to_node_map: Dict[str, str] = {}
        from app.schemas.review import NodeReviewState

        for anno in annos:
            category = AcademicNodeCategory(anno.academic_type)
            # Find matching text block to extract title
            target_block = next((b for b in doc.blocks if b.block_id == anno.target_id), None)
            title = target_block.text[:40] + "..." if (target_block and target_block.text and len(target_block.text) > 40) else (target_block.text if target_block else anno.academic_type)
            title = title or anno.academic_type

            node_id = f"an_{anno.target_id}"
            nodes.append(
                AcademicNode(
                    node_id=node_id,
                    category=category,
                    title=title,
                    target_block_id=anno.target_id,
                    anchor_key=anchor_map.get(anno.target_id),
                    review_state=NodeReviewState.UNREVIEWED,
                    metadata={"provenance": anno.provenance}
                )
            )
            block_to_node_map[anno.target_id] = node_id

        # 2. Build edges: parent-child structure mapping using DocumentGraph
        for anno in annos:
            node_id = block_to_node_map[anno.target_id]
            curr_id = anno.target_id

            # Walk up DocumentGraph to locate nearest enclosing academic parent heading
            parent_node_id = None
            while True:
                parent_block = doc_graph.get_parent(curr_id)
                if parent_block:
                    parent_block_id = parent_block.block_id
                    if parent_block_id in block_to_node_map:
                        parent_node_id = block_to_node_map[parent_block_id]
                        break
                    curr_id = parent_block_id
                else:
                    break

            if parent_node_id:
                edges.append(
                    AcademicEdge(
                        source_node_id=parent_node_id,
                        target_node_id=node_id,
                        edge_type="CONTAINS",
                        confidence=anno.confidence.score,
                    )
                )

        # 3. Cache compiled graph components in context
        context.shared_cache["academic_graph"] = {
            "nodes": nodes,
            "edges": edges,
        }
