import time
from typing import Dict, List, Optional, Tuple, Any

from app.schemas.document import BlockSchema, BlockType
from app.services.intelligence.base import BaseIntelligenceModule, ModuleMetadata
from app.services.intelligence.context import IntelligenceContext
from app.services.intelligence.annotations import ConfidenceScore, QualityAnnotation, HierarchyAnnotation
from app.services.intelligence.graph import (
    ReadingEdgeType,
    ReadingGraphEdge,
    DocumentReadingGraphAnnotation,
)
from app.services.intelligence.events import (
    ValidationStarted,
    ValidationWarning,
    ValidationCompleted,
)


class HierarchyValidationModule(BaseIntelligenceModule):
    """Runs logical tree cycle checks, detects structural orphans, and generates quality metrics."""

    def __init__(self):
        self._metadata = ModuleMetadata(
            name="HIERARCHY_VALIDATION_MODULE",
            version="1.0.0",
            author="LectureAI Core",
            stage="hierarchy_validation",
            priority=110,
            dependencies=[
                "FEATURE_EXTRACTION_MODULE",
                "HEADING_DETECTION_MODULE",
                "LIST_QUOTE_NOTE_DETECTION_MODULE",
                "TABLE_CAPTION_DETECTION_MODULE",
                "CODE_FORMULA_DETECTION_MODULE",
                "READING_ORDER_INTELLIGENCE_MODULE",
                "HIERARCHY_BUILDER_MODULE",
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
            context.event_publisher.publish(ValidationCompleted(upload_id=doc.upload_id if doc else "unknown"))
            return

        # Publish event: ValidationStarted
        context.event_publisher.publish(ValidationStarted(upload_id=doc.upload_id))

        # Fetch Graph and Hierarchy annotations from the store
        graphs = context.annotation_store.find_by_type(DocumentReadingGraphAnnotation)
        hierarchy_annos = context.annotation_store.find_by_type(HierarchyAnnotation)

        if not graphs or not hierarchy_annos:
            context.event_publisher.publish(ValidationCompleted(upload_id=doc.upload_id))
            return

        graph_anno = graphs[0]
        h_map = {a.target_id: a for a in hierarchy_annos}

        warnings: List[str] = []
        orphan_count = 0
        cycle_detected = False

        # Gather document configuration statistics
        has_headings = any(b.block_type == BlockType.HEADING for b in doc.blocks)
        total_headings = sum(1 for b in doc.blocks if b.block_type == BlockType.HEADING)

        # 1. Parent Edge Maps & Cycle Checks
        # Validate that parent links do not form circular paths
        for block in doc.blocks:
            b_id = block.block_id
            
            # DFS ancestor traversal to find cycles
            visited_ancestors = set()
            curr_id = block.parent_block_id
            while curr_id:
                if curr_id in visited_ancestors:
                    warnings.append(f"Cycle detected involving parent-child loop at block: {curr_id}")
                    context.event_publisher.publish(
                        ValidationWarning(
                            upload_id=doc.upload_id,
                            warning_type="cycle",
                            block_id=curr_id,
                        )
                    )
                    cycle_detected = True
                    break
                visited_ancestors.add(curr_id)
                
                # Fetch next ancestor parent
                h_node = h_map.get(curr_id)
                curr_id = h_node.parent_id if h_node else None

        # 2. Orphans Detection
        for block in doc.blocks:
            b_id = block.block_id
            b_type = block.block_type
            parent_id = block.parent_block_id

            if has_headings and parent_id is None:
                # Top-level sections (headings with level 1 or None if no structure) are expected to have parent=None.
                # However, regular paragraphs, tables, equations, code, or quotes with parent=None are orphans.
                if b_type not in (BlockType.HEADING, BlockType.HEADER, BlockType.FOOTER, BlockType.PAGE_NUMBER):
                    orphan_count += 1
                    warnings.append(f"Orphan block of type {b_type} found with no parent heading: {b_id}")
                    context.event_publisher.publish(
                        ValidationWarning(
                            upload_id=doc.upload_id,
                            warning_type=f"orphan_{b_type.lower()}",
                            block_id=b_id,
                        )
                    )

            # Check for orphan captions (captions not linked to any target)
            if b_type == BlockType.CAPTION and parent_id is None:
                orphan_count += 1
                warnings.append(f"Orphan caption block found with no associated target: {b_id}")
                context.event_publisher.publish(
                    ValidationWarning(
                        upload_id=doc.upload_id,
                        warning_type="orphan_caption",
                        block_id=b_id,
                    )
                )

        # 3. Heading nesting jump checks (e.g. H1 followed directly by H3 without H2)
        for block in doc.blocks:
            if block.block_type == BlockType.HEADING and block.heading_level is not None:
                parent_id = block.parent_block_id
                if parent_id:
                    parent_block = next((b for b in doc.blocks if b.block_id == parent_id), None)
                    if parent_block and parent_block.block_type == BlockType.HEADING and parent_block.heading_level is not None:
                        # Emits warnings if levels skip by > 1 step
                        if block.heading_level > parent_block.heading_level + 1:
                            warnings.append(
                                f"Heading level jump from H{parent_block.heading_level} to H{block.heading_level} at block {block.block_id}"
                            )
                            context.event_publisher.publish(
                                ValidationWarning(
                                    upload_id=doc.upload_id,
                                    warning_type="heading_jump",
                                    block_id=block.block_id,
                                )
                            )

        # 4. Graph Statistics calculation
        root_count = sum(1 for b in doc.blocks if b.parent_block_id is None)
        total_edges = len(graph_anno.edges)
        edge_types_counts = {}
        for edge in graph_anno.edges:
            edge_types_counts[edge.edge_type.value] = edge_types_counts.get(edge.edge_type.value, 0) + 1

        # Max Depth Calculation
        max_depth = 0
        for block in doc.blocks:
            h_node = h_map.get(block.block_id)
            if h_node:
                depth = h_node.metadata.get("depth", 0)
                if depth > max_depth:
                    max_depth = depth

        # Calculate logical consistency score
        block_count = len(doc.blocks)
        warning_count = len(warnings)
        consistency_score = 1.0 - min(1.0, warning_count / block_count) if block_count > 0 else 1.0

        # Store validation warnings in context diagnostics for engine retrieval
        context.diagnostics.extend([
            {"module": self.metadata.name, "warning": w} for w in warnings
        ])

        # 6. Save a Document-Wide QualityAnnotation
        quality_anno = QualityAnnotation(
            annotation_id=f"q_{doc.upload_id}_{int(time.time())}",
            target_id=doc.upload_id,
            provenance=self.metadata.name,
            confidence=ConfidenceScore(
                score=consistency_score,
                contributors={"consistency": consistency_score},
                method="rule_validation_metrics",
            ),
            is_scanned=False,
            metadata={
                "warning_count": warning_count,
                "orphan_count": orphan_count,
                "cycle_detected": cycle_detected,
                "max_depth": max_depth,
            }
        )
        context.annotation_store.add(quality_anno)

        # Publish event: ValidationCompleted
        context.event_publisher.publish(
            ValidationCompleted(
                upload_id=doc.upload_id,
                consistency_score=consistency_score,
                warning_count=warning_count
            )
        )
