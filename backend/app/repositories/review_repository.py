import time
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.review import AcademicOverride, AcademicAuditEntry, AcademicReviewRevision, AcademicGraphSnapshot


class ReviewRepository:
    """Repository managing ORM mapping queries and mutations for human validation overrides and audit trails."""

    def __init__(self, db: Session):
        self.db = db

    def get_or_create_revision(self, upload_id: str) -> int:
        """Fetch current concurrency revision or initialize it to 0 if not exists."""
        row = self.db.query(AcademicReviewRevision).filter(AcademicReviewRevision.upload_id == upload_id).first()
        if not row:
            row = AcademicReviewRevision(upload_id=upload_id, revision=0)
            self.db.add(row)
            try:
                self.db.flush()
            except Exception:
                # Handle unique constraint race condition
                self.db.rollback()
                row = self.db.query(AcademicReviewRevision).filter(AcademicReviewRevision.upload_id == upload_id).first()
                if not row:
                    raise
        return row.revision

    def increment_revision(self, upload_id: str, expected_revision: int) -> int:
        """Locks the revision row, verifies expectation, and increments revision monotonically."""
        # select for update to lock the row in concurrent databases
        row = (
            self.db.query(AcademicReviewRevision)
            .filter(AcademicReviewRevision.upload_id == upload_id)
            .with_for_update()
            .first()
        )
        if not row:
            # If not initialized, initialize it to 0
            row = AcademicReviewRevision(upload_id=upload_id, revision=0)
            self.db.add(row)
            self.db.flush()

        if row.revision != expected_revision:
            raise ValueError(f"Revision mismatch. Database is at {row.revision}, expected {expected_revision}")

        row.revision += 1
        self.db.flush()
        return row.revision

    def create_override(
        self,
        upload_id: str,
        target_anchor_key: str,
        action_type: str,
        payload: dict,
        target_block_id: Optional[str] = None,
    ) -> AcademicOverride:
        """Create a new manual academic override entry."""
        override = AcademicOverride(
            upload_id=upload_id,
            target_anchor_key=target_anchor_key,
            target_block_id=target_block_id,
            action_type=action_type,
            payload=payload,
            is_active=True,
            created_at=time.time(),
            updated_at=time.time(),
        )
        self.db.add(override)
        self.db.flush()  # Populates override.id
        return override

    def create_bulk_overrides(
        self,
        overrides_data: List[dict]
    ) -> None:
        """Create multiple manual academic override entries efficiently."""
        if not overrides_data:
            return
            
        overrides = []
        now = time.time()
        for data in overrides_data:
            overrides.append(
                AcademicOverride(
                    upload_id=data["upload_id"],
                    target_anchor_key=data["target_anchor_key"],
                    target_block_id=data.get("target_block_id"),
                    action_type=data["action_type"],
                    payload=data.get("payload", {}),
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            
        self.db.add_all(overrides)
        self.db.flush()

    def get_override_by_id(self, override_id: str) -> Optional[AcademicOverride]:
        """Fetch a specific manual override by its primary ID."""
        return self.db.query(AcademicOverride).filter(AcademicOverride.id == override_id).first()

    def get_active_overrides(self, upload_id: str) -> List[AcademicOverride]:
        """Fetch all active overrides for a document, ordered chronologically (oldest first)."""
        return (
            self.db.query(AcademicOverride)
            .filter(
                AcademicOverride.upload_id == upload_id,
                AcademicOverride.is_active == True,
            )
            .order_by(AcademicOverride.created_at.asc(), AcademicOverride.id.asc())
            .all()
        )

    def create_audit_entry(
        self,
        upload_id: str,
        user_id: str,
        action_type: str,
        node_id: str,
        previous_state: dict,
        new_state: dict,
        comment: Optional[str] = None,
    ) -> AcademicAuditEntry:
        """Create an append-only audit entry. Immutability is enforced at the database layer."""
        audit = AcademicAuditEntry(
            upload_id=upload_id,
            user_id=user_id,
            action_type=action_type,
            node_id=node_id,
            previous_state=previous_state,
            new_state=new_state,
            comment=comment,
            timestamp=time.time(),
        )
        self.db.add(audit)
        self.db.flush()  # Populates audit.id
        return audit

    def list_audit_entries_for_document(
        self, upload_id: str
    ) -> List[AcademicAuditEntry]:
        """List all audit logs for a given document upload, ordered chronologically."""
        return (
            self.db.query(AcademicAuditEntry)
            .filter(AcademicAuditEntry.upload_id == upload_id)
            .order_by(AcademicAuditEntry.timestamp.asc())
            .all()
        )

    def create_snapshot(
        self,
        upload_id: str,
        pipeline_run_id: str,
        approval_version: int,
        approved_revision: int,
        base_graph_fingerprint: str,
        resolved_graph_fingerprint: str,
        reviewer_id: str,
        nodes: list,
        edges: list,
    ) -> AcademicGraphSnapshot:
        """Create and persist an immutable approved snapshot of the resolved graph."""
        snapshot = AcademicGraphSnapshot(
            upload_id=upload_id,
            pipeline_run_id=pipeline_run_id,
            approval_version=approval_version,
            approved_revision=approved_revision,
            base_graph_fingerprint=base_graph_fingerprint,
            resolved_graph_fingerprint=resolved_graph_fingerprint,
            approval_timestamp=time.time(),
            reviewer_id=reviewer_id,
            nodes=nodes,
            edges=edges,
            schema_version="1.0.0",
        )
        self.db.add(snapshot)
        self.db.flush()
        return snapshot

    def get_snapshot(self, upload_id: str, version: int) -> Optional[AcademicGraphSnapshot]:
        """Retrieve a specific approved snapshot version."""
        return (
            self.db.query(AcademicGraphSnapshot)
            .filter(
                AcademicGraphSnapshot.upload_id == upload_id,
                AcademicGraphSnapshot.approval_version == version,
            )
            .first()
        )

    def get_latest_snapshot(self, upload_id: str) -> Optional[AcademicGraphSnapshot]:
        """Retrieve the latest approved snapshot version for a document."""
        return (
            self.db.query(AcademicGraphSnapshot)
            .filter(AcademicGraphSnapshot.upload_id == upload_id)
            .order_by(AcademicGraphSnapshot.approval_version.desc())
            .first()
        )

    def list_snapshots(self, upload_id: str) -> List[AcademicGraphSnapshot]:
        """List all approved snapshots for a document, ordered version ascending."""
        return (
            self.db.query(AcademicGraphSnapshot)
            .filter(AcademicGraphSnapshot.upload_id == upload_id)
            .order_by(AcademicGraphSnapshot.approval_version.asc())
            .all()
        )

    def get_next_approval_version(self, upload_id: str) -> int:
        """Get the next sequential approval version number for a document."""
        latest = self.get_latest_snapshot(upload_id)
        if not latest:
            return 1
        return latest.approval_version + 1
