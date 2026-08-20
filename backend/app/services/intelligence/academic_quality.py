import time
from typing import Dict, List, Any
from app.schemas.academic import AcademicNodeCategory
from app.services.intelligence.base import BaseIntelligenceModule, ModuleMetadata
from app.services.intelligence.context import IntelligenceContext
from app.services.intelligence.annotations import ConfidenceScore, QualityAnnotation


class AcademicQualityModule(BaseIntelligenceModule):
    """Evaluates curriculum completeness, academic coverage, concept density, and orphan nodes."""

    def __init__(self):
        self._metadata = ModuleMetadata(
            name="ACADEMIC_QUALITY_MODULE",
            version="1.0.0",
            author="LectureAI Core",
            stage="academic_quality_validation",
            priority=150,
            dependencies=["ACADEMIC_GRAPH_BUILDER_MODULE"],
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

        # Fetch compiled graph components
        graph_data = context.shared_cache.get("academic_graph", {"nodes": [], "edges": []})
        nodes = graph_data.get("nodes", [])
        edges = graph_data.get("edges", [])

        if not nodes:
            # Save basic null metric annotation
            anno = QualityAnnotation(
                annotation_id=f"ac_qual_{doc.upload_id}_{int(time.time())}",
                target_id=doc.upload_id,
                provenance=self.metadata.name,
                confidence=ConfidenceScore(score=1.0, method="null_academic_validation"),
                ocr_confidence_raw=1.0,
                metadata={"coverage": 1.0, "density": 0.0, "orphan_count": 0}
            )
            context.annotation_store.add(anno)
            return

        total_nodes = len(nodes)
        warnings: List[Dict[str, Any]] = []
        recommendations: List[Dict[str, Any]] = []

        # 1. Coverage analysis: Identify containers
        containers = [n for n in nodes if n.category in (AcademicNodeCategory.CHAPTER, AcademicNodeCategory.SECTION)]
        content_items = [n for n in nodes if n.category not in (AcademicNodeCategory.CHAPTER, AcademicNodeCategory.SECTION, AcademicNodeCategory.UNIT)]

        covered_containers = set()
        for edge in edges:
            if edge.edge_type == "CONTAINS" and edge.source_node_id in [c.node_id for c in containers]:
                # If target is a content item
                target_node = next((n for n in content_items if n.node_id == edge.target_node_id), None)
                if target_node:
                    covered_containers.add(edge.source_node_id)

        coverage = len(covered_containers) / len(containers) if containers else 1.0

        # 2. Orphans: Content items that have no parent container
        parented_node_ids = {e.target_node_id for e in edges if e.edge_type == "CONTAINS"}
        orphans = [n for n in content_items if n.node_id not in parented_node_ids]
        orphan_ratio = len(orphans) / len(content_items) if content_items else 0.0

        # 3. Density
        pages_count = getattr(doc.metadata, "page_count", 1) or 1
        density = len(content_items) / pages_count

        # 4. Cycle Detection inside graph hierarchy (DFS crawl)
        cycle_detected = False
        adj_list = {n.node_id: [] for n in nodes}
        for edge in edges:
            adj_list[edge.source_node_id].append(edge.target_node_id)

        visited = set()
        stack = set()

        def has_cycle(node_id: str) -> bool:
            visited.add(node_id)
            stack.add(node_id)
            for child in adj_list.get(node_id, []):
                if child not in visited:
                    if has_cycle(child):
                        return True
                elif child in stack:
                    return True
            stack.remove(node_id)
            return False

        for node in nodes:
            if node.node_id not in visited:
                if has_cycle(node.node_id):
                    cycle_detected = True
                    break

        cycle_ratio = 1.0 if cycle_detected else 0.0

        # Final quality calculation
        academic_score = coverage * (1.0 - orphan_ratio) * (1.0 - cycle_ratio)
        academic_score = max(0.0, min(1.0, academic_score))

        # Generate warnings
        if coverage < 0.50:
            warnings.append({
                "warning_code": "ACADEMIC_COVERAGE_LOW",
                "severity": "WARNING",
                "message": f"Pedagogical coverage is low: only {coverage * 100:.1f}% of chapters/sections contain teaching materials.",
                "target_id": doc.upload_id,
            })

        if len(orphans) > 0:
            warnings.append({
                "warning_code": "ORPHAN_ACADEMIC_NODES",
                "severity": "INFO",
                "message": f"Found {len(orphans)} orphan academic concepts not parented by any section heading.",
                "target_id": doc.upload_id,
            })

        if cycle_detected:
            warnings.append({
                "warning_code": "CYCLIC_ACADEMIC_RELATIONS",
                "severity": "CRITICAL",
                "message": "Pedagogical contains hierarchy cycles detected.",
                "target_id": doc.upload_id,
            })

        # Recommendations list
        if cycle_detected or orphan_ratio > 0.30:
            recommendations.append({
                "recommendation_code": "MANUAL_CURRICULUM_REVIEW",
                "severity": "WARNING",
                "message": "Academic validation failed. Manual verification of curriculum outline is recommended.",
                "target_id": doc.upload_id,
            })

        # Save QualityAnnotation into the store
        quality_anno = QualityAnnotation(
            annotation_id=f"ac_qual_{doc.upload_id}_{int(time.time())}",
            target_id=doc.upload_id,
            provenance=self.metadata.name,
            confidence=ConfidenceScore(
                score=academic_score,
                contributors={
                    "coverage": coverage,
                    "orphan_ratio": orphan_ratio,
                    "density": density,
                },
                method="academic_completeness_aggregation",
            ),
            metadata={
                "coverage": coverage,
                "density": density,
                "orphan_count": len(orphans),
                "warnings": warnings,
                "recommendations": recommendations,
            }
        )
        context.annotation_store.add(quality_anno)

        # Store warnings in context diagnostics list
        for w in warnings:
            context.diagnostics.append({
                "module": self.metadata.name,
                "warning": f"[{w['warning_code']}] {w['message']}"
            })
