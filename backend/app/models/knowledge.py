import uuid
import time
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    ForeignKey,
    Text,
    JSON,
    UniqueConstraint,
    ForeignKeyConstraint,
    event,
    DDL
)
from sqlalchemy.orm import relationship, Session
from app.models.document import Base


class KnowledgeVersion(Base):
    __tablename__ = "knowledge_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_id = Column(String(36), nullable=False, index=True)
    snapshot_id = Column(String(36), ForeignKey("academic_graph_snapshots.id", ondelete="RESTRICT"), nullable=False, index=True)
    schema_version = Column(String(32), default="1.0.0", nullable=False)
    created_at = Column(Float, default=lambda: time.time(), nullable=False)
    status = Column(String(32), default="BUILDING", nullable=False)  # "BUILDING" or "FINALIZED"
    metadata_json = Column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("snapshot_id", name="uq_kv_snapshot_id"),
    )

    # Relationships
    snapshot = relationship("AcademicGraphSnapshot")
    entities = relationship(
        "KnowledgeEntity",
        back_populates="version",
        cascade="all, delete-orphan",
        passive_deletes=True
    )
    relationships = relationship(
        "KnowledgeRelationship",
        back_populates="version",
        cascade="all, delete-orphan",
        passive_deletes=True
    )


class KnowledgeEntity(Base):
    __tablename__ = "knowledge_entities"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    knowledge_version_id = Column(
        String(36), ForeignKey("knowledge_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_type = Column(String(32), nullable=False)  # e.g., CONCEPT, DEFINITION, etc.
    title = Column(String(256), nullable=False)
    content = Column(Text, nullable=False)
    stable_id = Column(String(128), nullable=False, index=True)
    metadata_json = Column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("knowledge_version_id", "id", name="uq_entity_version_id"),
        UniqueConstraint("knowledge_version_id", "stable_id", name="uq_entity_version_stable"),
    )

    # Relationships
    version = relationship("KnowledgeVersion", back_populates="entities")
    evidence = relationship(
        "KnowledgeEvidence",
        back_populates="entity",
        cascade="all, delete-orphan",
        passive_deletes=True
    )
    source_relations = relationship(
        "KnowledgeRelationship",
        back_populates="source",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="[KnowledgeRelationship.source_entity_id]"
    )
    target_relations = relationship(
        "KnowledgeRelationship",
        back_populates="target",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="[KnowledgeRelationship.target_entity_id]"
    )


class KnowledgeRelationship(Base):
    __tablename__ = "knowledge_relationships"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    knowledge_version_id = Column(
        String(36), ForeignKey("knowledge_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_entity_id = Column(String(36), nullable=False, index=True)
    target_entity_id = Column(String(36), nullable=False, index=True)
    relationship_type = Column(String(64), nullable=False)
    confidence = Column(Float, default=1.0, nullable=False)
    is_inferred = Column(Boolean, default=False, nullable=False)
    is_human_confirmed = Column(Boolean, default=False, nullable=False)
    metadata_json = Column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "knowledge_version_id",
            "source_entity_id",
            "target_entity_id",
            "relationship_type",
            name="uq_rel_version_endpoints_type"
        ),
        ForeignKeyConstraint(
            ["knowledge_version_id", "source_entity_id"],
            ["knowledge_entities.knowledge_version_id", "knowledge_entities.id"],
            ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["knowledge_version_id", "target_entity_id"],
            ["knowledge_entities.knowledge_version_id", "knowledge_entities.id"],
            ondelete="CASCADE"
        ),
    )

    # Relationships
    version = relationship("KnowledgeVersion", back_populates="relationships")
    source = relationship(
        "KnowledgeEntity",
        back_populates="source_relations",
        foreign_keys=[source_entity_id]
    )
    target = relationship(
        "KnowledgeEntity",
        back_populates="target_relations",
        foreign_keys=[target_entity_id]
    )


class KnowledgeEvidence(Base):
    __tablename__ = "knowledge_evidence"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(
        String(36), ForeignKey("knowledge_entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id = Column(
        String(36), ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    page_number = Column(Integer, nullable=True)
    section_title = Column(String(256), nullable=True)
    source_node_id = Column(String(64), nullable=True)
    source_anchor_key = Column(String(64), nullable=True)
    text_reference = Column(Text, nullable=True)
    provenance = Column(String(64), nullable=False)  # e.g., EXPLICIT_CLASSIFIER, HUMAN_OVERRIDE
    
    # Layout Coordinates
    x0 = Column(Float, nullable=True)
    y0 = Column(Float, nullable=True)
    x1 = Column(Float, nullable=True)
    y1 = Column(Float, nullable=True)

    metadata_json = Column(JSON, nullable=True)

    # Relationships
    entity = relationship("KnowledgeEntity", back_populates="evidence")


# ─────────────────────────────────────────────────────────────────────────────
# APPLICATION-LEVEL LIFECYCLE IMMUTABILITY GUARDS
# ─────────────────────────────────────────────────────────────────────────────

def verify_version_not_finalized(session, version_id):
    """Raise ValueError if the target KnowledgeVersion is finalized."""
    if not version_id:
        return
    # Query directly to prevent dirty session state from bypassing check
    status = session.query(KnowledgeVersion.status).filter(KnowledgeVersion.id == version_id).scalar()
    if status == "FINALIZED":
        raise ValueError("Mutations on finalized knowledge versions are strictly prohibited.")


from sqlalchemy.orm.attributes import get_history

@event.listens_for(Session, "before_flush")
def check_finalized_mutations(session, flush_context, instances):
    for obj in session.new.union(session.dirty).union(session.deleted):
        if isinstance(obj, KnowledgeVersion):
            hist = get_history(obj, 'status')
            if hist.has_changes():
                old_status = hist.deleted[0] if hist.deleted else None
                if old_status == "FINALIZED":
                    raise ValueError("Mutations on finalized knowledge versions are strictly prohibited.")
            else:
                if obj.status == "FINALIZED" and (obj in session.dirty or obj in session.deleted):
                    raise ValueError("Mutations on finalized knowledge versions are strictly prohibited.")
        elif isinstance(obj, KnowledgeEntity):
            if obj in session.new:
                verify_version_not_finalized(session, obj.knowledge_version_id)
            else:
                hist = get_history(obj, 'knowledge_version_id')
                verify_version_not_finalized(session, obj.knowledge_version_id)
                if hist.deleted:
                    verify_version_not_finalized(session, hist.deleted[0])
        elif isinstance(obj, KnowledgeRelationship):
            if obj.source_entity_id == obj.target_entity_id:
                raise ValueError("Self-referencing relationships are strictly prohibited.")
            if obj in session.new:
                verify_version_not_finalized(session, obj.knowledge_version_id)
            else:
                hist = get_history(obj, 'knowledge_version_id')
                verify_version_not_finalized(session, obj.knowledge_version_id)
                if hist.deleted:
                    verify_version_not_finalized(session, hist.deleted[0])
        elif isinstance(obj, KnowledgeEvidence):
            entity_id = obj.entity_id
            entity = session.query(KnowledgeEntity).filter(KnowledgeEntity.id == entity_id).first()
            if entity:
                verify_version_not_finalized(session, entity.knowledge_version_id)
            else:
                hist = get_history(obj, 'entity_id')
                ent_ids = [entity_id]
                if hist.deleted:
                    ent_ids.extend(hist.deleted)
                for eid in ent_ids:
                    ent = session.query(KnowledgeEntity).filter(KnowledgeEntity.id == eid).first()
                    if ent:
                        verify_version_not_finalized(session, ent.knowledge_version_id)


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE-LEVEL TRIGGERS (SQLITE ENGINE GUARD)
# ─────────────────────────────────────────────────────────────────────────────

# SQLite triggers
sqlite_version_update_trigger = DDL("""
CREATE TRIGGER IF NOT EXISTS kv_block_update
BEFORE UPDATE ON knowledge_versions
WHEN OLD.status = 'FINALIZED'
BEGIN
    SELECT RAISE(FAIL, 'Updates to finalized knowledge versions are prohibited.');
END;
""")

sqlite_version_delete_trigger = DDL("""
CREATE TRIGGER IF NOT EXISTS kv_block_delete
BEFORE DELETE ON knowledge_versions
WHEN OLD.status = 'FINALIZED'
BEGIN
    SELECT RAISE(FAIL, 'Deletions of finalized knowledge versions are prohibited.');
END;
""")

sqlite_entity_update_trigger = DDL("""
CREATE TRIGGER IF NOT EXISTS ke_block_update
BEFORE UPDATE ON knowledge_entities
WHEN (SELECT status FROM knowledge_versions WHERE id = OLD.knowledge_version_id) = 'FINALIZED'
BEGIN
    SELECT RAISE(FAIL, 'Updates to entities in finalized knowledge versions are prohibited.');
END;
""")

sqlite_entity_delete_trigger = DDL("""
CREATE TRIGGER IF NOT EXISTS ke_block_delete
BEFORE DELETE ON knowledge_entities
WHEN (SELECT status FROM knowledge_versions WHERE id = OLD.knowledge_version_id) = 'FINALIZED'
BEGIN
    SELECT RAISE(FAIL, 'Deletions of entities in finalized knowledge versions are prohibited.');
END;
""")

sqlite_rel_update_trigger = DDL("""
CREATE TRIGGER IF NOT EXISTS kr_block_update
BEFORE UPDATE ON knowledge_relationships
WHEN (SELECT status FROM knowledge_versions WHERE id = OLD.knowledge_version_id) = 'FINALIZED'
BEGIN
    SELECT RAISE(FAIL, 'Updates to relationships in finalized knowledge versions are prohibited.');
END;
""")

sqlite_rel_delete_trigger = DDL("""
CREATE TRIGGER IF NOT EXISTS kr_block_delete
BEFORE DELETE ON knowledge_relationships
WHEN (SELECT status FROM knowledge_versions WHERE id = OLD.knowledge_version_id) = 'FINALIZED'
BEGIN
    SELECT RAISE(FAIL, 'Deletions of relationships in finalized knowledge versions are prohibited.');
END;
""")

sqlite_ev_update_trigger = DDL("""
CREATE TRIGGER IF NOT EXISTS kev_block_update
BEFORE UPDATE ON knowledge_evidence
WHEN (SELECT kv.status FROM knowledge_versions kv JOIN knowledge_entities ke ON ke.knowledge_version_id = kv.id WHERE ke.id = OLD.entity_id) = 'FINALIZED'
BEGIN
    SELECT RAISE(FAIL, 'Updates to evidence in finalized knowledge versions are prohibited.');
END;
""")

sqlite_ev_delete_trigger = DDL("""
CREATE TRIGGER IF NOT EXISTS kev_block_delete
BEFORE DELETE ON knowledge_evidence
WHEN (SELECT kv.status FROM knowledge_versions kv JOIN knowledge_entities ke ON ke.knowledge_version_id = kv.id WHERE ke.id = OLD.entity_id) = 'FINALIZED'
BEGIN
    SELECT RAISE(FAIL, 'Deletions of evidence in finalized knowledge versions are prohibited.');
END;
""")

# Register triggers on tables
for trigger in [sqlite_version_update_trigger, sqlite_version_delete_trigger]:
    event.listen(KnowledgeVersion.__table__, "after_create", trigger.execute_if(dialect="sqlite"))

for trigger in [sqlite_entity_update_trigger, sqlite_entity_delete_trigger]:
    event.listen(KnowledgeEntity.__table__, "after_create", trigger.execute_if(dialect="sqlite"))

for trigger in [sqlite_rel_update_trigger, sqlite_rel_delete_trigger]:
    event.listen(KnowledgeRelationship.__table__, "after_create", trigger.execute_if(dialect="sqlite"))

for trigger in [sqlite_ev_update_trigger, sqlite_ev_delete_trigger]:
    event.listen(KnowledgeEvidence.__table__, "after_create", trigger.execute_if(dialect="sqlite"))


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE-LEVEL TRIGGERS (POSTGRESQL ENGINE GUARD)
# ─────────────────────────────────────────────────────────────────────────────

postgres_func_ddl = DDL("""
CREATE OR REPLACE FUNCTION block_finalized_knowledge_mutations()
RETURNS TRIGGER AS $$
DECLARE
    v_status VARCHAR(32);
BEGIN
    IF TG_TABLE_NAME = 'knowledge_versions' THEN
        v_status := OLD.status;
    ELSIF TG_TABLE_NAME = 'knowledge_entities' THEN
        SELECT status INTO v_status FROM knowledge_versions WHERE id = OLD.knowledge_version_id;
    ELSIF TG_TABLE_NAME = 'knowledge_relationships' THEN
        SELECT status INTO v_status FROM knowledge_versions WHERE id = OLD.knowledge_version_id;
    ELSIF TG_TABLE_NAME = 'knowledge_evidence' THEN
        SELECT kv.status INTO v_status FROM knowledge_versions kv
        JOIN knowledge_entities ke ON ke.knowledge_version_id = kv.id
        WHERE ke.id = OLD.entity_id;
    END IF;

    IF v_status = 'FINALIZED' THEN
        RAISE EXCEPTION 'Operations on finalized knowledge versions are strictly prohibited.';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""")

# Listeners to execute function creation on first table setup
event.listen(KnowledgeVersion.__table__, "after_create", postgres_func_ddl.execute_if(dialect="postgresql"))

postgres_kv_trigger = DDL("""
CREATE TRIGGER kv_finalized_guard
BEFORE UPDATE OR DELETE ON knowledge_versions
FOR EACH ROW EXECUTE FUNCTION block_finalized_knowledge_mutations();
""")
postgres_ke_trigger = DDL("""
CREATE TRIGGER ke_finalized_guard
BEFORE UPDATE OR DELETE ON knowledge_entities
FOR EACH ROW EXECUTE FUNCTION block_finalized_knowledge_mutations();
""")
postgres_kr_trigger = DDL("""
CREATE TRIGGER kr_finalized_guard
BEFORE UPDATE OR DELETE ON knowledge_relationships
FOR EACH ROW EXECUTE FUNCTION block_finalized_knowledge_mutations();
""")
postgres_kev_trigger = DDL("""
CREATE TRIGGER kev_finalized_guard
BEFORE UPDATE OR DELETE ON knowledge_evidence
FOR EACH ROW EXECUTE FUNCTION block_finalized_knowledge_mutations();
""")

event.listen(KnowledgeVersion.__table__, "after_create", postgres_kv_trigger.execute_if(dialect="postgresql"))
event.listen(KnowledgeEntity.__table__, "after_create", postgres_ke_trigger.execute_if(dialect="postgresql"))
event.listen(KnowledgeRelationship.__table__, "after_create", postgres_kr_trigger.execute_if(dialect="postgresql"))
event.listen(KnowledgeEvidence.__table__, "after_create", postgres_kev_trigger.execute_if(dialect="postgresql"))
