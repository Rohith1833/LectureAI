from collections import defaultdict
import time
from typing import Any, Dict, List, Set
from loguru import logger

from app.services.intelligence.base import BaseIntelligenceModule
from app.services.intelligence.context import IntelligenceContext
from app.services.intelligence.config import IntelligenceConfig
from app.services.intelligence.exceptions import CircularDependencyError, ModuleExecutionError
from app.services.intelligence.events import (
    PipelineEventPublisher,
    PipelineStarted,
    ModuleStarted,
    ModuleFinished,
    ModuleSkipped,
    ModuleFailed,
    PipelineFinished,
)
from app.services.intelligence.report import IntelligenceReport, ModuleMetrics
from app.services.intelligence.annotations import QualityAnnotation, HierarchyAnnotation
from app.services.intelligence.graph import DocumentReadingGraphAnnotation


class DependencyResolver:
    """Computes topological execution ordering for registered modules based on declared dependencies."""

    @staticmethod
    def resolve(modules: List[BaseIntelligenceModule]) -> List[BaseIntelligenceModule]:
        adj: Dict[str, Set[str]] = defaultdict(set)
        in_degree: Dict[str, int] = {m.metadata.name: 0 for m in modules}
        module_map = {m.metadata.name: m for m in modules}

        for m in modules:
            for dep in m.metadata.dependencies:
                # If dependency is not in active registry, fail resolution
                if dep not in module_map:
                    raise ValueError(f"Required dependency '{dep}' for module '{m.metadata.name}' is missing.")
                adj[dep].add(m.metadata.name)
                in_degree[m.metadata.name] += 1

        # Kahn's Algorithm
        queue = [name for name, degree in in_degree.items() if degree == 0]
        # Sort queue alphabetically to make order deterministic when priority is equal
        queue.sort()
        order = []

        while queue:
            curr = queue.pop(0)
            order.append(module_map[curr])
            # Process neighbors
            neighbors = sorted(list(adj[curr]))
            for neighbor in neighbors:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(modules):
            raise CircularDependencyError("Circular dependency detected in intelligence pipeline modules.")

        return order


class IntelligenceEngine:
    """Manages ordered pipeline execution, lifecycle updates, error isolation, and metrics tracking."""

    def __init__(self, config: IntelligenceConfig):
        self.config = config
        self.publisher = PipelineEventPublisher()

    def execute(
        self,
        document: Any,
        page_metadata: Dict[int, Any],
        document_metadata: Any,
        modules: List[BaseIntelligenceModule],
        upload_id: str
    ) -> tuple[IntelligenceContext, IntelligenceReport]:
        start_time = time.time()
        
        # 1. Initialize Context
        context = IntelligenceContext(
            document=document,
            page_metadata=page_metadata,
            document_metadata=document_metadata,
            settings=self.config
        )

        # 2. Filter enabled modules
        active_modules = []
        skipped_module_names = []
        for m in modules:
            # Check override in config
            module_cfg = self.config.modules.get(m.metadata.name)
            enabled = module_cfg.enabled if module_cfg else m.metadata.enabled
            if enabled:
                active_modules.append(m)
            else:
                skipped_module_names.append(m.metadata.name)
                self.publisher.publish(
                    ModuleSkipped(upload_id=upload_id, module_name=m.metadata.name, reason="Disabled in config")
                )

        # 3. Resolve Execution Sequence DAG
        try:
            execution_order = DependencyResolver.resolve(active_modules)
        except Exception as e:
            logger.error(f"Failed to resolve module dependencies: {str(e)}")
            self.publisher.publish(
                PipelineFinished(
                    upload_id=upload_id,
                    total_time_ms=0.0,
                    success=False,
                    annotations_count=0
                )
            )
            raise e

        # Publish Pipeline Started Event
        order_names = [m.metadata.name for m in execution_order]
        self.publisher.publish(PipelineStarted(upload_id=upload_id, execution_order=order_names))

        module_metrics_map: Dict[str, ModuleMetrics] = {
            name: ModuleMetrics(
                module_name=name,
                execution_time_ms=0.0,
                success=True,
                annotations_generated=0,
                skipped=True
            ) for name in skipped_module_names
        }
        pipeline_success = True

        # 4. Pipeline Execution Loop
        for module in execution_order:
            module_name = module.metadata.name
            module_cfg = self.config.modules.get(module_name)
            module_params = module_cfg.parameters if module_cfg else {}

            self.publisher.publish(ModuleStarted(upload_id=upload_id, module_name=module_name))
            
            m_start = time.time()
            m_success = False
            m_error = None
            m_warnings = []
            anno_start_count = len(context.annotation_store.statistics()["type_counts"])

            try:
                # Initialize
                module.initialize(module_params)
                
                # Execute
                module.execute(context)
                
                # Validate
                if not module.validate(context):
                    raise ModuleExecutionError(f"Validation failed inside module '{module_name}'.")
                
                # Cleanup
                module.cleanup()
                
                m_success = True
                m_duration = (time.time() - m_start) * 1000.0
                
                # Metrics compilation
                anno_end_count = len(context.annotation_store.statistics()["type_counts"])
                generated_count = len(context.annotation_store.find_by_target("*")) or 0 # approximate or custom track
                # Let's count actual delta or total annotations for this provenance
                my_annos = [a for a in context.annotation_store.query(lambda x: x.provenance == module_name)]
                
                self.publisher.publish(
                    ModuleFinished(
                        upload_id=upload_id,
                        module_name=module_name,
                        execution_time_ms=m_duration,
                        annotations_generated=len(my_annos)
                    )
                )

            except Exception as e:
                m_duration = (time.time() - m_start) * 1000.0
                m_error = str(e)
                logger.error(f"Module '{module_name}' failed: {m_error}")

                # Determine if fatal (if strict mode is active, or if it is configured as strict module)
                is_fatal = self.config.strict_mode or (module_cfg.strict if module_cfg else False)
                self.publisher.publish(
                    ModuleFailed(
                        upload_id=upload_id,
                        module_name=module_name,
                        error_message=m_error,
                        fatal=is_fatal
                    )
                )

                if is_fatal:
                    pipeline_success = False
                    module_metrics_map[module_name] = ModuleMetrics(
                        module_name=module_name,
                        execution_time_ms=m_duration,
                        success=False,
                        annotations_generated=0,
                        error_message=m_error
                    )
                    break
                else:
                    m_warnings.append(f"Ignored soft failure: {m_error}")

            # Register Metrics
            my_annos = [a for a in context.annotation_store.query(lambda x: x.provenance == module_name)]
            diag_warnings = [
                d["warning"] for d in context.diagnostics
                if d.get("module") == module_name and "warning" in d
            ]
            m_warnings.extend(diag_warnings)
            module_metrics_map[module_name] = ModuleMetrics(
                module_name=module_name,
                execution_time_ms=m_duration,
                success=m_success,
                annotations_generated=len(my_annos),
                error_message=m_error,
                warnings=m_warnings
            )

        # 5. Compile Pipeline Telemetry & Stats
        total_duration = (time.time() - start_time) * 1000.0
        all_annos = context.annotation_store.query(lambda x: True)
        
        # Calculate overall confidence score average
        avg_confidence = 0.0
        if all_annos:
            avg_confidence = sum(a.confidence.score for a in all_annos) / len(all_annos)

        self.publisher.publish(
            PipelineFinished(
                upload_id=upload_id,
                total_time_ms=total_duration,
                success=pipeline_success,
                annotations_count=len(all_annos)
            )
        )

        # Extract quality validation metrics if present
        hierarchy_depth = None
        total_sections = None
        orphan_count = None
        graph_statistics = None
        root_count = None
        hierarchy_consistency_score = None

        ocr_quality_score = None
        layout_quality_score = None
        semantic_quality_score = None
        hierarchy_quality_score = None
        reading_quality_score = None
        overall_quality_score = None
        quality_warnings = []
        processing_recommendations = []

        quality_annos = context.annotation_store.find_by_type(QualityAnnotation)
        
        # Validation annotation (from hierarchy validator step)
        val_anno = next((q for q in quality_annos if q.provenance == "HIERARCHY_VALIDATION_MODULE"), None)
        if val_anno:
            hierarchy_consistency_score = val_anno.confidence.score
            orphan_count = val_anno.metadata.get("orphan_count")
            hierarchy_depth = val_anno.metadata.get("max_depth")

        # Document Quality annotation (from quality analyzer step)
        doc_q_anno = next((q for q in quality_annos if q.provenance == "DOCUMENT_QUALITY_MODULE"), None)
        if doc_q_anno:
            ocr_quality_score = doc_q_anno.ocr_quality_score
            layout_quality_score = doc_q_anno.layout_quality_score
            semantic_quality_score = doc_q_anno.semantic_quality_score
            hierarchy_quality_score = doc_q_anno.hierarchy_quality_score
            reading_quality_score = doc_q_anno.reading_quality_score
            overall_quality_score = doc_q_anno.overall_quality_score
            quality_warnings = doc_q_anno.metadata.get("warnings", [])
            processing_recommendations = doc_q_anno.metadata.get("recommendations", [])

        # Academic Quality annotation (from academic quality validation step)
        academic_quality_score = None
        academic_coverage_score = None
        academic_density_score = None
        academic_orphan_count = None
        academic_warnings = []
        academic_recommendations = []

        acad_q_anno = next((q for q in quality_annos if q.provenance == "ACADEMIC_QUALITY_MODULE"), None)
        if acad_q_anno:
            academic_quality_score = acad_q_anno.confidence.score
            academic_coverage_score = acad_q_anno.confidence.contributors.get("coverage")
            academic_density_score = acad_q_anno.confidence.contributors.get("density")
            academic_orphan_count = acad_q_anno.metadata.get("orphan_count")
            academic_warnings = acad_q_anno.metadata.get("warnings", [])
            academic_recommendations = acad_q_anno.metadata.get("recommendations", [])

        hierarchy_annos = context.annotation_store.find_by_type(HierarchyAnnotation)
        if hierarchy_annos:
            from app.schemas.document import BlockType
            # Count sections (HEADING blocks)
            # Find matching headings in doc
            total_sections = sum(
                1 for b in context.document.blocks
                if b.block_type == BlockType.HEADING
            )
            root_count = sum(1 for a in hierarchy_annos if a.parent_id is None)

        graphs = context.annotation_store.find_by_type(DocumentReadingGraphAnnotation)
        if graphs:
            graph_anno = graphs[0]
            total_edges = len(graph_anno.edges)
            edge_types_counts = {}
            for edge in graph_anno.edges:
                edge_types_counts[edge.edge_type.value] = edge_types_counts.get(edge.edge_type.value, 0) + 1
            graph_statistics = {
                "total_nodes": len(graph_anno.nodes),
                "total_edges": total_edges,
                "edge_types": edge_types_counts,
            }

        report = IntelligenceReport(
            upload_id=upload_id,
            execution_order=order_names,
            metrics=module_metrics_map,
            total_time_ms=total_duration,
            overall_confidence_average=avg_confidence,
            success=pipeline_success,
            hierarchy_depth=hierarchy_depth,
            total_sections=total_sections,
            orphan_count=orphan_count,
            graph_statistics=graph_statistics,
            root_count=root_count,
            hierarchy_consistency_score=hierarchy_consistency_score,
            ocr_quality_score=ocr_quality_score,
            layout_quality_score=layout_quality_score,
            semantic_quality_score=semantic_quality_score,
            hierarchy_quality_score=hierarchy_quality_score,
            reading_quality_score=reading_quality_score,
            overall_quality_score=overall_quality_score,
            quality_warnings=quality_warnings,
            processing_recommendations=processing_recommendations,
            academic_quality_score=academic_quality_score,
            academic_coverage_score=academic_coverage_score,
            academic_density_score=academic_density_score,
            academic_orphan_count=academic_orphan_count,
            academic_warnings=academic_warnings,
            academic_recommendations=academic_recommendations,
        )

        return context, report
