import time
import logging

_log = logging.getLogger(__name__)
from typing import List, Dict, Any, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.schemas.academic import AcademicNode, AcademicEdge, AcademicNodeCategory
from app.schemas.review import ReconciliationStatus, ResolvedGraphResult, NodeReviewState, DocumentReviewState, ApprovalCheck, ApprovalReadiness
from app.models.review import AcademicOverride, AcademicAuditEntry, AcademicGraphSnapshot, AcademicReviewRevision
from app.repositories.document_repository import DocumentRepository
from app.repositories.review_repository import ReviewRepository
from app.services.intelligence.review.overlay import AcademicOverlayService, calculate_graph_fingerprint
from app.schemas.document import DocumentExtractionResult, DocumentMetadataSchema, PageSchema, BlockSchema, BoundingBox, BlockType


def orm_to_extraction_result(doc) -> DocumentExtractionResult:
    """Helper to map SQLAlchemy ORM Document back to Pydantic DocumentExtractionResult."""
    pages = [
        PageSchema(
            page_number=p.page_number,
            width=p.width,
            height=p.height,
            extra_metadata=p.extra_metadata or {}
        ) for p in doc.pages
    ]
    
    blocks = [
        BlockSchema(
            block_id=b.id,
            page_number=b.page_number,
            reading_order=b.reading_order,
            block_type=BlockType(b.block_type),
            text=b.text,
            bounding_box=BoundingBox(x0=b.x0, y0=b.y0, x1=b.x1, y1=b.y1),
            font_size=b.font_size,
            font_family=b.font_family,
            bold=b.bold,
            italic=b.italic,
            confidence=b.confidence,
            parent_block_id=b.parent_block_id,
            previous_block_id=b.previous_block_id,
            next_block_id=b.next_block_id,
            heading_level=b.heading_level,
            extra_metadata=b.extra_metadata or {},
            provenance=b.provenance
        ) for b in doc.blocks
    ]
    
    metadata = DocumentMetadataSchema(
        title=doc.metadata_rel.title if doc.metadata_rel else None,
        author=doc.metadata_rel.author if doc.metadata_rel else None,
        subject=doc.metadata_rel.subject if doc.metadata_rel else None,
        keywords=doc.metadata_rel.keywords if doc.metadata_rel else None,
        creation_date=doc.metadata_rel.creation_date if doc.metadata_rel else None,
        producer=doc.metadata_rel.producer if doc.metadata_rel else None,
        page_count=doc.metadata_rel.page_count if doc.metadata_rel else 0,
        pdf_version=doc.metadata_rel.pdf_version if doc.metadata_rel else None,
        language=doc.metadata_rel.language if doc.metadata_rel else None,
        extra_metadata=doc.metadata_rel.extra_metadata if doc.metadata_rel else None
    )
    
    return DocumentExtractionResult(
        upload_id=doc.upload_id,
        status=doc.status,
        metadata=metadata,
        pages=pages,
        blocks=blocks,
        tables=[],
        images=[],
        extraction_timestamp=doc.extraction_timestamp,
        processing_time=doc.processing_time,
        ocr_status=doc.ocr_status,
        ocr_engine=doc.ocr_engine,
        ocr_version=doc.ocr_version,
        ocr_confidence=doc.ocr_confidence,
        ocr_language=doc.ocr_language,
        ocr_processing_time=doc.ocr_processing_time,
        extra_metadata=doc.extra_metadata or {}
    )


# Module-level static in-memory cache to prevent redundant academic graph pipeline re-compilation
_BASE_GRAPH_CACHE: Dict[str, tuple[List[AcademicNode], List[AcademicEdge]]] = {}


class AcademicReviewService:
    """Service layer managing review state summaries, query filters, audit trails, and optimistic concurrency."""

    def __init__(self, db: Session):
        self.db = db
        self.doc_repo = DocumentRepository(db)
        self.review_repo = ReviewRepository(db)
        self.overlay_service = AcademicOverlayService()

    def get_base_graph(self, upload_id: str) -> tuple[List[AcademicNode], List[AcademicEdge]]:
        """Loads and compiles base AcademicGraph in-memory using Phase 4/5A pipeline modules."""
        doc = self.doc_repo.get_document_by_upload_id(upload_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found.")

        # Multi-worker safe cache key using document extraction timestamp
        cache_key = f"{upload_id}:{doc.extraction_timestamp}"
        if cache_key in _BASE_GRAPH_CACHE:
            import copy
            cached_nodes, cached_edges = _BASE_GRAPH_CACHE[cache_key]
            return copy.deepcopy(cached_nodes), copy.deepcopy(cached_edges)

        pydantic_doc = orm_to_extraction_result(doc)
        
        # Load core pipeline engines dynamically
        from app.services.intelligence.config import IntelligenceConfig
        from app.services.intelligence.engine import IntelligenceEngine
        from app.services.intelligence import (
            FeatureExtractionModule,
            HeadingDetectionModule,
            ListQuoteNoteDetectionModule,
            TableCaptionDetectionModule,
            CodeFormulaDetectionModule,
            ReadingOrderIntelligenceModule,
            HierarchyBuilderModule,
            HierarchyValidationModule,
            DocumentQualityModule,
            AcademicFeatureEngine,
            CurriculumClassificationModule,
            ExpositoryClassificationModule,
            PedagogicalClassificationModule,
            AcademicGraphBuilderModule,
            AcademicQualityModule,
        )

        config = IntelligenceConfig(modules={})
        engine = IntelligenceEngine(config)
        
        modules = [
            FeatureExtractionModule(),
            HeadingDetectionModule(),
            ListQuoteNoteDetectionModule(),
            TableCaptionDetectionModule(),
            CodeFormulaDetectionModule(),
            ReadingOrderIntelligenceModule(),
            HierarchyBuilderModule(),
            HierarchyValidationModule(),
            DocumentQualityModule(),
            AcademicFeatureEngine(),
            CurriculumClassificationModule(),
            ExpositoryClassificationModule(),
            PedagogicalClassificationModule(),
            AcademicGraphBuilderModule(),
            AcademicQualityModule(),
        ]
        
        page_metadata = {p.page_number: p for p in pydantic_doc.pages}
        context, report = engine.execute(
            document=pydantic_doc,
            page_metadata=page_metadata,
            document_metadata=pydantic_doc.metadata,
            modules=modules,
            upload_id=upload_id
        )
        
        graph_data = context.shared_cache.get("academic_graph", {"nodes": [], "edges": []})
        nodes, edges = graph_data["nodes"], graph_data["edges"]
        cache_key = f"{upload_id}:{doc.extraction_timestamp}"
        _BASE_GRAPH_CACHE[cache_key] = (nodes, edges)
        
        import copy
        return copy.deepcopy(nodes), copy.deepcopy(edges)

    def get_review_summary(self, upload_id: str) -> Dict[str, Any]:
        """Fetch high-level document review status, node stats, and warnings."""
        base_nodes, base_edges = self.get_base_graph(upload_id)
        active_overrides = self.review_repo.get_active_overrides(upload_id)
        
        result = self.overlay_service.compile_resolved_graph(base_nodes, base_edges, active_overrides)
        
        # Node stats compilation
        total_nodes = len(result.nodes)
        unreviewed = sum(1 for n in result.nodes if n.review_state == NodeReviewState.UNREVIEWED)
        accepted = sum(1 for n in result.nodes if n.review_state == NodeReviewState.ACCEPTED)
        modified = sum(1 for n in result.nodes if n.review_state == NodeReviewState.MODIFIED)
        
        # Include hidden/rejected nodes count
        # In base graph but not in resolved graph (excluding manually created ones)
        resolved_node_ids = {n.node_id for n in result.nodes}
        rejected = sum(1 for n in base_nodes if n.node_id not in resolved_node_ids)

        # Document review state determination from database
        doc_model = self.doc_repo.get_document_by_upload_id(upload_id)
        doc_state = DocumentReviewState.NEEDS_REVIEW
        if doc_model and doc_model.review_state:
            try:
                doc_state = DocumentReviewState(doc_model.review_state)
            except ValueError:
                pass

        # Authoritative eligibility readiness check
        readiness = self.check_approval_readiness(upload_id)
        is_ready = readiness["eligible"]

        # Historical snapshots list
        snapshots = self.review_repo.list_snapshots(upload_id)
        history_data = [
            {
                "approval_version": f"v{s.approval_version}",
                "approved_revision": s.approved_revision,
                "pipeline_run_id": s.pipeline_run_id,
                "approval_timestamp": s.approval_timestamp,
                "reviewer_id": s.reviewer_id,
                "resolved_graph_fingerprint": s.resolved_graph_fingerprint
            }
            for s in snapshots
        ]

        return {
            "upload_id": upload_id,
            "document_id": doc_model.id if doc_model else None,
            "document_review_state": doc_state.value,
            "base_graph_fingerprint": result.base_graph_fingerprint,
            "resolved_graph_fingerprint": result.resolved_graph_fingerprint,
            "reconciliation_status": result.reconciliation_status.value,
            "total_nodes": total_nodes,
            "unreviewed_count": unreviewed,
            "accepted_count": accepted,
            "modified_count": modified,
            "rejected_count": rejected,
            "stale_overrides_count": len(result.stale_override_ids),
            "conflicted_overrides_count": len(result.conflicted_override_ids),
            "approval_readiness": is_ready,
            "warnings": result.validation_warnings,
            "errors": result.validation_errors,
            "resolved_graph_version": self.review_repo.get_or_create_revision(upload_id),
            "pipeline_run_id": doc_model.extraction_timestamp if doc_model else "",
            "approval_history": history_data
        }

    def get_resolved_graph(
        self,
        upload_id: str,
        limit: int = 100,
        offset: int = 0,
        category: Optional[str] = None,
        review_state: Optional[str] = None,
        low_confidence: Optional[bool] = None,
        orphan: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Fetch resolved graph nodes and edges with filtering and pagination."""
        base_nodes, base_edges = self.get_base_graph(upload_id)
        active_overrides = self.review_repo.get_active_overrides(upload_id)
        
        result = self.overlay_service.compile_resolved_graph(base_nodes, base_edges, active_overrides)
        
        # Pre-build parent containment mapping for orphan filtering
        child_to_parent = {}
        for edge in result.edges:
            if edge.edge_type == "CONTAINS":
                child_to_parent[edge.target_node_id] = edge.source_node_id

        # Apply filters on resolved nodes
        filtered_nodes = []
        for n in result.nodes:
            if category and n.category.value != category:
                continue
            if review_state and n.review_state.value != review_state:
                continue
            if low_confidence is not None:
                conf = n.metadata.get("confidence", 1.0)
                is_low = conf < 0.65
                if is_low != low_confidence:
                    continue
            if orphan is not None:
                is_orphan = n.node_id not in child_to_parent
                # Headings at the very top (UNIT) are allowed to be orphans, but topic/definition should have parent
                if is_orphan != orphan:
                    continue
            filtered_nodes.append(n)

        # Slice nodes pagination
        paginated_nodes = filtered_nodes[offset : offset + limit]
        paginated_node_ids = {n.node_id for n in paginated_nodes}

        # Filter edges to only include relationships connected to paginated nodes
        # or optionally return all edges that connect active nodes
        filtered_edges = [
            e for e in result.edges
            if e.source_node_id in paginated_node_ids or e.target_node_id in paginated_node_ids
        ]

        return {
            "nodes": [n.model_dump() for n in paginated_nodes],
            "edges": [e.model_dump() for e in filtered_edges],
            "total_count": len(filtered_nodes),
            "resolved_graph_version": self.review_repo.get_or_create_revision(upload_id)
        }

    def get_node_details(self, upload_id: str, node_id: str) -> Dict[str, Any]:
        """Retrieve detailed metadata, provenance, original values, and audit trace for a node."""
        base_nodes, base_edges = self.get_base_graph(upload_id)
        active_overrides = self.review_repo.get_active_overrides(upload_id)
        
        result = self.overlay_service.compile_resolved_graph(base_nodes, base_edges, active_overrides)
        
        # Find resolved node
        node = next((n for n in result.nodes if n.node_id == node_id), None)
        if not node:
            # Check if it was deleted/rejected
            node = next((n for n in base_nodes if n.node_id == node_id), None)
            if not node:
                raise HTTPException(status_code=404, detail="Node not found.")

        # Find parent node ID
        parent_id = None
        for edge in result.edges:
            if edge.edge_type == "CONTAINS" and edge.target_node_id == node_id:
                parent_id = edge.source_node_id
                break

        # Find child node IDs
        child_ids = [
            e.target_node_id for e in result.edges
            if e.edge_type == "CONTAINS" and e.source_node_id == node_id
        ]

        # Retrieve audit entries for this specific node
        all_audits = self.review_repo.list_audit_entries_for_document(upload_id)
        node_audits = [a for a in all_audits if a.node_id == node_id]

        return {
            "node_id": node.node_id,
            "category": node.category.value,
            "title": node.title,
            "review_state": node.review_state.value,
            "confidence": node.metadata.get("confidence", 1.0),
            "provenance": node.metadata.get("provenance", "AUTOMATIC"),
            "anchor_key": node.anchor_key,
            "target_block_id": node.target_block_id,
            "original_values": {
                "category": node.metadata.get("original_category", node.category.value),
                "title": node.metadata.get("original_title", node.title),
                "parent_id": node.metadata.get("original_parent_id", None)
            },
            "parent_id": parent_id,
            "child_ids": child_ids,
            "override_ids": node.metadata.get("override_ids", []),
            "audit_history": [
                {
                    "audit_id": a.id,
                    "user_id": a.user_id,
                    "action_type": a.action_type,
                    "previous_state": a.previous_state,
                    "new_state": a.new_state,
                    "comment": a.comment,
                    "timestamp": a.timestamp
                } for a in node_audits
            ]
        }

    def apply_review_action(
        self,
        upload_id: str,
        action_type: str,
        payload: dict,
        expected_version: int,
        user_id: str,
        comment: Optional[str] = None
    ) -> Dict[str, Any]:
        """Enforces optimistic concurrency control and commits corrections and audits atomically."""
        # 1. Fetch active overrides to compile the resolved graph
        active_overrides = self.review_repo.get_active_overrides(upload_id)

        # 2. Get base graph to resolve the target node state
        base_nodes, base_edges = self.get_base_graph(upload_id)
        resolved_result = self.overlay_service.compile_resolved_graph(base_nodes, base_edges, active_overrides)
        
        # 3. Derive previous and new state parameters based on action type
        previous_state = {}
        new_state = {}
        target_node_id = ""
        target_anchor = payload.get("target_anchor_key")

        if action_type == "CREATE_NODE":
            target_node_id = f"an_manual_temp"  # temp placeholder until override is committed
            previous_state = {}
            new_state = {
                "category": payload.get("category"),
                "title": payload.get("title"),
                "target_block_id": payload.get("target_block_id")
            }
        else:
            # Resolve target node
            if not target_anchor:
                raise HTTPException(status_code=400, detail="Missing target_anchor_key in mutation payload.")
            
            node_map = {n.node_id: n for n in resolved_result.nodes}
            target_node = next((n for n in resolved_result.nodes if n.anchor_key == target_anchor), None)
            if not target_node:
                raise HTTPException(status_code=404, detail="Target node not found in compiled graph.")
            
            target_node_id = target_node.node_id

            if action_type == "CHANGE_CATEGORY":
                previous_state = {"category": target_node.category.value}
                new_state = {"category": payload.get("new_category")}
            elif action_type == "RENAME_TITLE":
                previous_state = {"title": target_node.title}
                new_state = {"title": payload.get("new_title")}
            elif action_type == "REPARENT_NODE":
                # Find current parent
                current_parent_id = None
                for edge in resolved_result.edges:
                    if edge.edge_type == "CONTAINS" and edge.target_node_id == target_node_id:
                        current_parent_id = edge.source_node_id
                        break
                previous_state = {"parent_id": current_parent_id}
                new_state = {"parent_id": payload.get("new_parent_id")}
            elif action_type == "DELETE_NODE":
                previous_state = {"review_state": target_node.review_state.value}
                new_state = {"review_state": NodeReviewState.REJECTED.value}
            elif action_type == "ACCEPT_NODE":
                previous_state = {"review_state": target_node.review_state.value}
                new_state = {"review_state": NodeReviewState.ACCEPTED.value}
            elif action_type == "UPDATE_EDGE":
                # Edges update
                previous_state = {}
                new_state = payload

        # 4. Atomic Transaction execution (commits override, audit entry, and revision increment)
        try:
            # Enforce optimistic concurrency control by locking and incrementing the revision row
            new_rev = self.review_repo.increment_revision(upload_id, expected_version)

            override = self.review_repo.create_override(
                upload_id=upload_id,
                target_anchor_key=target_anchor or f"anc_manual_{int(time.time())}",
                action_type=action_type,
                payload=payload,
                target_block_id=payload.get("target_block_id")
            )
            
            # Re-update node_id in audit if it was created
            if action_type == "CREATE_NODE":
                target_node_id = f"an_manual_{override.id}"

            self.review_repo.create_audit_entry(
                upload_id=upload_id,
                user_id=user_id,
                action_type=action_type,
                node_id=target_node_id,
                previous_state=previous_state,
                new_state=new_state,
                comment=comment
            )
            self.db.commit()
            
            # Invalidate base graph cache entries for this upload
            keys_to_del = [k for k in _BASE_GRAPH_CACHE.keys() if k.startswith(f"{upload_id}:")]
            for k in keys_to_del:
                _BASE_GRAPH_CACHE.pop(k, None)
        except ValueError as ve:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Optimistic Concurrency Control conflict. {str(ve)}"
            )
        except Exception as e:
            self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Database transaction atomic commit failed: {str(e)}")

        return {
            "success": True,
            "override_id": override.id,
            "new_version": new_rev
        }

    def get_reconciliation_info(self, upload_id: str) -> Dict[str, Any]:
        """Expose detailed stale, ambiguous, and conflicting overrides listings for the UI."""
        base_nodes, base_edges = self.get_base_graph(upload_id)
        active_overrides = self.review_repo.get_active_overrides(upload_id)
        
        result = self.overlay_service.compile_resolved_graph(base_nodes, base_edges, active_overrides)
        
        stale_list = []
        for o in active_overrides:
            if o.id in result.stale_override_ids:
                stale_list.append({
                    "override_id": o.id,
                    "anchor_key": o.target_anchor_key,
                    "action_type": o.action_type,
                    "payload": o.payload,
                    "reason": "Target anchor key not found in the newly generated base graph (likely content deleted or renamed)."
                })

        conflicted_list = []
        for o in active_overrides:
            if o.id in result.conflicted_override_ids:
                conflicted_list.append({
                    "override_id": o.id,
                    "anchor_key": o.target_anchor_key,
                    "action_type": o.action_type,
                    "payload": o.payload,
                    "reason": "Ambiguous matching or logical collision with other active user actions."
                })

        return {
            "upload_id": upload_id,
            "reconciliation_status": result.reconciliation_status.value,
            "stale_overrides": stale_list,
            "conflicted_overrides": conflicted_list,
            "validation_errors": result.validation_errors,
            "validation_warnings": result.validation_warnings
        }

    def check_approval_readiness(self, upload_id: str) -> Dict[str, Any]:
        """Verify all approval preconditions and return structured checks list."""
        doc = self.doc_repo.get_document_by_upload_id(upload_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document upload not found.")
            
        base_nodes, base_edges = self.get_base_graph(upload_id)
        active_overrides = self.review_repo.get_active_overrides(upload_id)
        result = self.overlay_service.compile_resolved_graph(base_nodes, base_edges, active_overrides)
        
        checks = []

        # Check 1: UNREVIEWED_NODES
        unreviewed_count = sum(1 for n in result.nodes if n.review_state == NodeReviewState.UNREVIEWED)
        checks.append(ApprovalCheck(
            code="UNREVIEWED_NODES",
            passed=(unreviewed_count == 0),
            severity="BLOCKER",
            message=f"{unreviewed_count} nodes remain unreviewed." if unreviewed_count > 0 else "All academic nodes have been reviewed."
        ))

        # Check 2: STALE_OVERRIDES
        stale_count = len(result.stale_override_ids)
        checks.append(ApprovalCheck(
            code="STALE_OVERRIDES",
            passed=(stale_count == 0),
            severity="BLOCKER",
            message=f"{stale_count} stale overrides detected." if stale_count > 0 else "Zero stale overrides."
        ))

        # Check 3: OVERRIDE_CONFLICT
        conflict_count = len(result.conflicted_override_ids)
        checks.append(ApprovalCheck(
            code="OVERRIDE_CONFLICT",
            passed=(conflict_count == 0),
            severity="BLOCKER",
            message=f"{conflict_count} conflicted overrides detected." if conflict_count > 0 else "Zero active override conflicts."
        ))

        # Check 4: GRAPH_CYCLE
        has_cycle = self.overlay_service.detect_cycle(result.nodes, result.edges)
        checks.append(ApprovalCheck(
            code="GRAPH_CYCLE",
            passed=(not has_cycle),
            severity="BLOCKER",
            message="Containment cycle detected in the academic hierarchy." if has_cycle else "No hierarchy cycles detected."
        ))

        # Check 5: INVALID_GRAPH
        has_val_errors = len(result.validation_errors) > 0
        checks.append(ApprovalCheck(
            code="INVALID_GRAPH",
            passed=(not has_val_errors),
            severity="BLOCKER",
            message="; ".join(result.validation_errors) if has_val_errors else "Academic graph structure is valid."
        ))

        # Check 6: INVALID_PIPELINE_RUN
        is_processed = doc.status == "processed"
        checks.append(ApprovalCheck(
            code="INVALID_PIPELINE_RUN",
            passed=is_processed,
            severity="BLOCKER",
            message="Document processing pipeline is incomplete or failed." if not is_processed else "Document pipeline run completed successfully."
        ))

        # Check 7: ORPHAN_ACADEMIC_NODE
        child_to_parent = {}
        for edge in result.edges:
            if edge.edge_type == "CONTAINS":
                child_to_parent[edge.target_node_id] = edge.source_node_id
        
        orphans = []
        for n in result.nodes:
            if n.category != AcademicNodeCategory.UNIT and n.node_id not in child_to_parent:
                orphans.append(n.title)
        
        has_orphans = len(orphans) > 0
        checks.append(ApprovalCheck(
            code="ORPHAN_ACADEMIC_NODE",
            passed=(not has_orphans),
            severity="WARNING",
            message=f"Orphan non-unit nodes found: {', '.join(orphans)}" if has_orphans else "No orphan non-unit nodes detected."
        ))

        # Check 8: ACADEMIC_WARNING
        has_val_warnings = len(result.validation_warnings) > 0
        checks.append(ApprovalCheck(
            code="ACADEMIC_WARNING",
            passed=(not has_val_warnings),
            severity="WARNING",
            message="; ".join(result.validation_warnings) if has_val_warnings else "No academic quality warnings."
        ))

        blocking_reasons = [c.message for c in checks if not c.passed and c.severity == "BLOCKER"]
        warnings = [c.message for c in checks if not c.passed and c.severity == "WARNING"]
        eligible = (len(blocking_reasons) == 0)

        return {
            "eligible": eligible,
            "checks": [c.model_dump() for c in checks],
            "blocking_reasons": blocking_reasons,
            "warnings": warnings,
            "current_revision": self.review_repo.get_or_create_revision(upload_id),
            "resolved_graph_fingerprint": result.resolved_graph_fingerprint
        }

    def approve_resolved_graph(self, upload_id: str, expected_revision: int, user_id: str) -> Dict[str, Any]:
        """Atomically lock revision, check readiness, generate snapshot, transition state, and commit."""
        try:
            # 1. Lock review revision row
            db_revision = (
                self.db.query(AcademicReviewRevision)
                .filter(AcademicReviewRevision.upload_id == upload_id)
                .with_for_update()
                .first()
            )
            current_rev = db_revision.revision if db_revision else 0
            if current_rev != expected_revision:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Optimistic Concurrency Control conflict. Revision mismatch. Database is at {current_rev}, expected {expected_revision}"
                )

            # 2. Run readiness check
            readiness = self.check_approval_readiness(upload_id)
            if not readiness["eligible"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Document is not eligible for approval. Blocking reasons: {', '.join(readiness['blocking_reasons'])}"
                )

            # 3. Compile resolved graph
            base_nodes, base_edges = self.get_base_graph(upload_id)
            active_overrides = self.review_repo.get_active_overrides(upload_id)
            result = self.overlay_service.compile_resolved_graph(base_nodes, base_edges, active_overrides)

            # 4. Serialize deterministically
            nodes_data = []
            for n in sorted(result.nodes, key=lambda x: x.node_id):
                nodes_data.append({
                    "node_id": n.node_id,
                    "category": n.category.value,
                    "title": n.title,
                    "target_block_id": n.target_block_id,
                    "anchor_key": n.anchor_key,
                    "review_state": n.review_state.value,
                    "metadata": n.metadata
                })

            edges_data = []
            for e in sorted(result.edges, key=lambda x: (x.source_node_id, x.target_node_id)):
                edges_data.append({
                    "source_node_id": e.source_node_id,
                    "target_node_id": e.target_node_id,
                    "edge_type": e.edge_type,
                    "confidence": e.confidence,
                    "metadata": getattr(e, "metadata", {})
                })

            # 5. Allocate approval version
            next_version = self.review_repo.get_next_approval_version(upload_id)
            doc = self.doc_repo.get_document_by_upload_id(upload_id)
            pipeline_run_id = doc.extraction_timestamp

            # 6. Save immutable snapshot
            snapshot = self.review_repo.create_snapshot(
                upload_id=upload_id,
                pipeline_run_id=pipeline_run_id,
                approval_version=next_version,
                approved_revision=expected_revision,
                base_graph_fingerprint=result.base_graph_fingerprint,
                resolved_graph_fingerprint=result.resolved_graph_fingerprint,
                reviewer_id=user_id,
                nodes=nodes_data,
                edges=edges_data
            )

            # 7. Create audit log
            self.review_repo.create_audit_entry(
                upload_id=upload_id,
                user_id=user_id,
                action_type="APPROVE_GRAPH",
                node_id="upload_root",
                previous_state={"review_state": doc.review_state},
                new_state={"review_state": "APPROVED", "approval_version": next_version},
                comment=f"Approved graph version v{next_version}."
            )

            # 8. Transition Document state to APPROVED
            doc.review_state = "APPROVED"

            # 9. Increment review revision to R + 1
            if not db_revision:
                db_revision = AcademicReviewRevision(upload_id=upload_id, revision=0)
                self.db.add(db_revision)
                self.db.flush()
            db_revision.revision += 1

            # 10. Invalidate cache
            keys_to_del = [k for k in _BASE_GRAPH_CACHE.keys() if k.startswith(f"{upload_id}:")]
            for k in keys_to_del:
                _BASE_GRAPH_CACHE.pop(k, None)

            self.db.commit()
            return {
                "success": True,
                "approval_version": f"v{next_version}",
                "approved_revision": expected_revision,
                "resolved_graph_fingerprint": result.resolved_graph_fingerprint
            }
        except Exception as e:
            self.db.rollback()
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(status_code=500, detail=f"Approval transaction failed: {str(e)}")

    def validate_approval_after_rerun(self, upload_id: str):
        """Pipeline rerun boundary hook: check if existing approval remains valid."""
        doc = self.doc_repo.get_document_by_upload_id(upload_id)
        if not doc or doc.review_state != "APPROVED":
            return

        latest_snapshot = self.review_repo.get_latest_snapshot(upload_id)
        if not latest_snapshot:
            doc.review_state = "NEEDS_REVIEW"
            self.db.commit()
            return

        # Compile new resolved graph using new base graph + overrides
        base_nodes, base_edges = self.get_base_graph(upload_id)
        active_overrides = self.review_repo.get_active_overrides(upload_id)
        result = self.overlay_service.compile_resolved_graph(base_nodes, base_edges, active_overrides)

        is_still_valid = True
        
        # Invalidate only if resolved fingerprint changes, or new unreviewed nodes, or conflicts/stales appear
        if result.resolved_graph_fingerprint != latest_snapshot.resolved_graph_fingerprint:
            is_still_valid = False
            _log.info(
                "Approval invalidated: resolved graph fingerprint changed from %s to %s",
                latest_snapshot.resolved_graph_fingerprint, result.resolved_graph_fingerprint
            )
        
        unreviewed = sum(1 for n in result.nodes if n.review_state == NodeReviewState.UNREVIEWED)
        if unreviewed > 0:
            is_still_valid = False
            _log.info("Approval invalidated: %d new unreviewed nodes found.", unreviewed)

        if result.reconciliation_status != ReconciliationStatus.CLEAN:
            is_still_valid = False
            _log.info("Approval invalidated: reconciliation status is %s", result.reconciliation_status.value)

        if not is_still_valid:
            doc.review_state = "NEEDS_REVIEW"
            self.db.commit()
            # Clear uvicorn cache
            keys_to_del = [k for k in _BASE_GRAPH_CACHE.keys() if k.startswith(f"{upload_id}:")]
            for k in keys_to_del:
                _BASE_GRAPH_CACHE.pop(k, None)

    def get_approved_snapshot(self, upload_id: str, version: Optional[int] = None) -> Optional[AcademicGraphSnapshot]:
        """Phase 6 boundary read interface."""
        if version is not None:
            return self.review_repo.get_snapshot(upload_id, version)
        return self.review_repo.get_latest_snapshot(upload_id)

