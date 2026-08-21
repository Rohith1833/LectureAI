import uuid
import time
from sqlalchemy import Column, String, Boolean, Float, JSON, Text, Integer, event, DDL, UniqueConstraint
from app.models.document import Base


class AcademicOverride(Base):
    __tablename__ = "academic_overrides"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_id = Column(String(36), nullable=False, index=True)
    target_anchor_key = Column(String(64), nullable=False, index=True)
    target_block_id = Column(String(36), nullable=True)
    action_type = Column(String(32), nullable=False)  # e.g., "CHANGE_CATEGORY", "REPARENT_NODE"
    payload = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(Float, default=lambda: time.time())
    updated_at = Column(Float, default=lambda: time.time())


class AcademicAuditEntry(Base):
    __tablename__ = "academic_audit_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(64), nullable=False)
    action_type = Column(String(32), nullable=False)
    node_id = Column(String(64), nullable=False)
    previous_state = Column(JSON, nullable=False)
    new_state = Column(JSON, nullable=False)
    comment = Column(Text, nullable=True)
    timestamp = Column(Float, default=lambda: time.time(), index=True)


# Compound Indexing for optimal review patterns
event.listen(
    AcademicOverride.__table__,
    "after_create",
    DDL("CREATE INDEX IF NOT EXISTS idx_override_upload_anchor ON academic_overrides (upload_id, target_anchor_key);")
)

event.listen(
    AcademicAuditEntry.__table__,
    "after_create",
    DDL("CREATE INDEX IF NOT EXISTS idx_audit_upload_timestamp ON academic_audit_entries (upload_id, timestamp);")
)

# SQLite Immutability Triggers
sqlite_update_trigger = DDL("""
CREATE TRIGGER IF NOT EXISTS audit_log_block_update
BEFORE UPDATE ON academic_audit_entries
BEGIN
    SELECT RAISE(FAIL, 'Audit log table academic_audit_entries is append-only. UPDATE operations are prohibited.');
END;
""")

sqlite_delete_trigger = DDL("""
CREATE TRIGGER IF NOT EXISTS audit_log_block_delete
BEFORE DELETE ON academic_audit_entries
BEGIN
    SELECT RAISE(FAIL, 'Audit log table academic_audit_entries is append-only. DELETE operations are prohibited.');
END;
""")

# PostgreSQL Immutability Triggers
postgres_trigger_func = DDL("""
CREATE OR REPLACE FUNCTION block_audit_mutations()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit log table academic_audit_entries is append-only. UPDATE, DELETE, or TRUNCATE operations are strictly prohibited.';
END;
$$ LANGUAGE plpgsql;
""")

postgres_trigger = DDL("""
CREATE TRIGGER audit_log_append_only
BEFORE UPDATE OR DELETE ON academic_audit_entries
FOR EACH ROW EXECUTE FUNCTION block_audit_mutations();
""")

# Bind DDL scripts dynamically based on active connection dialect
event.listen(
    AcademicAuditEntry.__table__,
    "after_create",
    sqlite_update_trigger.execute_if(dialect="sqlite")
)
event.listen(
    AcademicAuditEntry.__table__,
    "after_create",
    sqlite_delete_trigger.execute_if(dialect="sqlite")
)
event.listen(
    AcademicAuditEntry.__table__,
    "after_create",
    postgres_trigger_func.execute_if(dialect="postgresql")
)
event.listen(
    AcademicAuditEntry.__table__,
    "after_create",
    postgres_trigger.execute_if(dialect="postgresql")
)


class AcademicReviewRevision(Base):
    __tablename__ = "academic_review_revisions"

    upload_id = Column(String(36), primary_key=True)
    revision = Column(Integer, default=0, nullable=False)


class AcademicGraphSnapshot(Base):
    __tablename__ = "academic_graph_snapshots"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_id = Column(String(36), nullable=False, index=True)
    pipeline_run_id = Column(String(36), nullable=False)
    approval_version = Column(Integer, nullable=False)
    approved_revision = Column(Integer, nullable=False)
    base_graph_fingerprint = Column(String(64), nullable=False)
    resolved_graph_fingerprint = Column(String(64), nullable=False)
    approval_timestamp = Column(Float, nullable=False)
    reviewer_id = Column(String(64), nullable=False)
    nodes = Column(JSON, nullable=False)
    edges = Column(JSON, nullable=False)
    schema_version = Column(String(32), default="1.0.0", nullable=False)

    __table_args__ = (
        UniqueConstraint("upload_id", "approval_version", name="uq_upload_version"),
    )


# SQLite Immutability Triggers for academic_graph_snapshots
snapshot_sqlite_update = DDL("""
CREATE TRIGGER IF NOT EXISTS snapshot_block_update
BEFORE UPDATE ON academic_graph_snapshots
BEGIN
    SELECT RAISE(FAIL, 'Table academic_graph_snapshots is append-only. UPDATE operations are prohibited.');
END;
""")

snapshot_sqlite_delete = DDL("""
CREATE TRIGGER IF NOT EXISTS snapshot_block_delete
BEFORE DELETE ON academic_graph_snapshots
BEGIN
    SELECT RAISE(FAIL, 'Table academic_graph_snapshots is append-only. DELETE operations are prohibited.');
END;
""")

# PostgreSQL Immutability Triggers for academic_graph_snapshots
snapshot_postgres_trigger = DDL("""
CREATE TRIGGER snapshot_append_only
BEFORE UPDATE OR DELETE ON academic_graph_snapshots
FOR EACH ROW EXECUTE FUNCTION block_audit_mutations();
""")

# Bind snapshot DDL scripts
event.listen(
    AcademicGraphSnapshot.__table__,
    "after_create",
    snapshot_sqlite_update.execute_if(dialect="sqlite")
)
event.listen(
    AcademicGraphSnapshot.__table__,
    "after_create",
    snapshot_sqlite_delete.execute_if(dialect="sqlite")
)
event.listen(
    AcademicGraphSnapshot.__table__,
    "after_create",
    snapshot_postgres_trigger.execute_if(dialect="postgresql")
)

