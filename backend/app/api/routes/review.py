from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.services.intelligence.review.service import AcademicReviewService
from app.schemas.review import ReconciliationStatus, ResolvedGraphResult

router = APIRouter(prefix="/academic")


class ReviewActionRequest(BaseModel):
    action_type: str = Field(
        ...,
        description="Supported review action: ACCEPT_NODE, CHANGE_CATEGORY, RENAME_TITLE, REPARENT_NODE, CREATE_NODE, DELETE_NODE, UPDATE_EDGE"
    )
    payload: dict = Field(
        default_factory=dict,
        description="Override attributes (e.g. new_category, new_title, new_parent_id, source_anchor)"
    )
    expected_version: int = Field(
        ...,
        description="OCC version count to prevent concurrent edits collision"
    )
    comment: Optional[str] = Field(
        None,
        description="Optional reviewer annotation comment explaining correction rationale"
    )


@router.get("/review/{upload_id}")
def get_review_summary(upload_id: str, db: Session = Depends(get_db)):
    """Fetch high-level document review status, node counts, and warnings."""
    service = AcademicReviewService(db)
    summary = service.get_review_summary(upload_id)
    return {"success": True, "data": summary}


@router.get("/review/{upload_id}/graph")
def get_resolved_graph(
    upload_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    category: Optional[str] = Query(None),
    review_state: Optional[str] = Query(None),
    low_confidence: Optional[bool] = Query(None),
    orphan: Optional[bool] = Query(None),
    db: Session = Depends(get_db)
):
    """Retrieve resolved AcademicGraph nodes and edges with filtering and pagination."""
    service = AcademicReviewService(db)
    graph_res = service.get_resolved_graph(
        upload_id=upload_id,
        limit=limit,
        offset=offset,
        category=category,
        review_state=review_state,
        low_confidence=low_confidence,
        orphan=orphan
    )
    return {"success": True, "data": graph_res}


@router.get("/review/{upload_id}/nodes/{node_id}")
def get_node_details(upload_id: str, node_id: str, db: Session = Depends(get_db)):
    """Retrieve detailed metadata, original values, and audit trace for a specific academic node."""
    service = AcademicReviewService(db)
    details = service.get_node_details(upload_id, node_id)
    return {"success": True, "data": details}


@router.post("/review/{upload_id}/actions")
def apply_review_action(
    upload_id: str,
    request: ReviewActionRequest,
    db: Session = Depends(get_db)
):
    """Enforce optimistic concurrency control and atomically write overrides and immutable audit logs."""
    # trusted reviewer identity boundary check
    # Extension Point: Replace hardcoded value with request.state.user.id extracted from JWT tokens
    trusted_user_id = "trusted_reviewer_user"
    
    service = AcademicReviewService(db)
    try:
        res = service.apply_review_action(
            upload_id=upload_id,
            action_type=request.action_type,
            payload=request.payload,
            expected_version=request.expected_version,
            user_id=trusted_user_id,
            comment=request.comment
        )
        return {"success": True, "data": res}
    except HTTPException as he:
        raise he
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Action compilation failed: {str(ex)}"
        )


@router.get("/review/{upload_id}/reconciliation")
def get_reconciliation(upload_id: str, db: Session = Depends(get_db)):
    """Retrieve lists of stale, ambiguous, and conflicting overrides for reconciliation UI display."""
    service = AcademicReviewService(db)
    recon = service.get_reconciliation_info(upload_id)
    return {"success": True, "data": recon}


@router.get("/review/{upload_id}/audit")
def get_audit_history(
    upload_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Retrieve chronological read-only audit log entries for a document."""
    service = AcademicReviewService(db)
    audits = service.review_repo.list_audit_entries_for_document(upload_id)
    
    # Apply pagination slice
    paginated_audits = audits[offset : offset + limit]
    
    data = [
        {
            "audit_id": a.id,
            "user_id": a.user_id,
            "action_type": a.action_type,
            "node_id": a.node_id,
            "previous_state": a.previous_state,
            "new_state": a.new_state,
            "comment": a.comment,
            "timestamp": a.timestamp
        }
        for a in paginated_audits
    ]
    return {
        "success": True,
        "data": {
            "audits": data,
            "total_count": len(audits)
        }
    }


class ApprovalRequest(BaseModel):
    expected_revision: int = Field(
        ...,
        description="OCC expected revision level matching current mutable state"
    )


@router.get("/review/{upload_id}/approval-readiness")
def get_approval_readiness(upload_id: str, db: Session = Depends(get_db)):
    """Get structured readiness checklist evaluation result."""
    service = AcademicReviewService(db)
    readiness = service.check_approval_readiness(upload_id)
    return {"success": True, "data": readiness}


@router.post("/review/{upload_id}/approve")
def approve_academic_graph(
    upload_id: str,
    request: ApprovalRequest,
    db: Session = Depends(get_db)
):
    """Approve the current AcademicGraph resolved state and create an immutable snapshot."""
    trusted_user_id = "trusted_reviewer_user"
    service = AcademicReviewService(db)
    res = service.approve_resolved_graph(
        upload_id=upload_id,
        expected_revision=request.expected_revision,
        user_id=trusted_user_id
    )
    return {"success": True, "data": res}


@router.get("/graph/{upload_id}")
def get_approved_graph(
    upload_id: str,
    version: Optional[str] = Query(None, description="Approval version, e.g., 'v1' or '1'"),
    db: Session = Depends(get_db)
):
    """Phase 6 boundary read interface: fetch approved snapshot by version."""
    version_num = None
    if version:
        v_str = version.lower().strip()
        if v_str.startswith("v"):
            v_str = v_str[1:]
        try:
            version_num = int(v_str)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid version format. Use e.g. 'v1' or '1'."
            )

    service = AcademicReviewService(db)
    snapshot = service.get_approved_snapshot(upload_id, version_num)
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No approved academic graph snapshot found for this document or version."
        )

    return {
        "success": True,
        "data": {
            "upload_id": snapshot.upload_id,
            "approval_version": f"v{snapshot.approval_version}",
            "pipeline_run_id": snapshot.pipeline_run_id,
            "approval_timestamp": snapshot.approval_timestamp,
            "reviewer_id": snapshot.reviewer_id,
            "resolved_graph_fingerprint": snapshot.resolved_graph_fingerprint,
            "schema_version": snapshot.schema_version,
            "nodes": snapshot.nodes,
            "edges": snapshot.edges
        }
    }
