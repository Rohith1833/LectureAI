"""
Phase 2 Test Suite: Academic structure preservation, source ordering, and corrected knowledge-version creation.

Verifies:
A. UNIT survives compilation.
B. UNIT -> CHAPTER -> SECTION -> TOPIC -> CONCEPT retains valid structure.
C. Chapter-only input remains chapters and is identified as Chapters mode.
D. Input without usable containers yields review-required behaviour.
E. Out-of-order UUIDs and shuffled entity insertion do not change source ordering.
F. Multiple source positions use the earliest actual tuple.
G. Missing positions/manual containers follow the documented fallback.
H. Evidence preserves correct document IDs, source pages, and provenance.
I. Compiling the same snapshot twice remains idempotent.
J. Re-approval creates new snapshot/version identities while prior finalized content remains unchanged.
K. Existing immutability protections still reject prohibited changes.
"""

import os
import uuid
import time
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models import Base, Document, AcademicGraphSnapshot, DocumentBlock, DocumentPage
from app.models.knowledge import (
    KnowledgeVersion,
    KnowledgeEntity,
    KnowledgeRelationship,
    KnowledgeEvidence
)
from app.services.intelligence.knowledge_builder import KnowledgeBuilder
from app.services.intelligence.knowledge_ordering import (
    compute_canonical_source_position,
    resolve_node_source_positions,
    sort_entities_by_source_order,
    get_selectable_containers,
    SelectableContainerMode,
)
from app.repositories.knowledge_repository import KnowledgeRepository
from app.schemas.knowledge import KnowledgeRelationshipType, KnowledgeEvidenceProvenance


@pytest.fixture
def db_session():
    """Isolated SQLite database with foreign keys and immutability triggers enabled."""
    db_file = f"test_phase2_{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except Exception:
                pass


def create_test_document(db, upload_id=None, doc_id=None):
    """Helper to create an approved Document with distinct doc_id and upload_id."""
    upload_id = upload_id or f"upload-{uuid.uuid4()}"
    doc_id = doc_id or f"doc-{uuid.uuid4()}"
    assert doc_id != upload_id

    doc = Document(
        id=doc_id,
        upload_id=upload_id,
        status="processed",
        extraction_timestamp=f"2026-09-28T12:00:00Z",
        processing_time=1.0,
        review_state="APPROVED"
    )
    db.add(doc)
    db.flush()

    page = DocumentPage(
        id=f"page-{uuid.uuid4()}",
        document_id=doc.id,
        page_number=1,
        width=612.0,
        height=792.0
    )
    db.add(page)
    db.flush()

    return doc, page


def create_block(db, doc, page, block_id, page_number, reading_order, text="Block text", block_type="PARAGRAPH"):
    """Helper to create a document block with explicit coordinates and reading order."""
    block = DocumentBlock(
        id=block_id,
        document_id=doc.id,
        page_id=page.id,
        page_number=page_number,
        reading_order=reading_order,
        block_type=block_type,
        text=text,
        x0=10.0,
        y0=20.0,
        x1=110.0,
        y1=120.0,
        provenance="NATIVE"
    )
    db.add(block)
    db.flush()
    return block


class TestPhase2KnowledgeCompilation:
    """Comprehensive test suite for Phase 2 compiler contracts, hierarchy, and ordering."""

    def test_a_unit_survives_compilation(self, db_session):
        """A. Verify UNIT category survives compilation into KnowledgeEntity and preserves attributes."""
        doc, page = create_test_document(db_session)
        block = create_block(db_session, doc, page, "blk_unit_1", page_number=1, reading_order=1, text="Unit 1 Heading", block_type="HEADING")

        snapshot = AcademicGraphSnapshot(
            upload_id=doc.upload_id,
            pipeline_run_id="run_1",
            approval_version=1,
            approved_revision=1,
            base_graph_fingerprint="bfp1",
            resolved_graph_fingerprint="rfp1",
            approval_timestamp=time.time(),
            reviewer_id="reviewer_1",
            nodes=[
                {
                    "node_id": "an_unit_1",
                    "category": "UNIT",
                    "title": "Unit 1: Fundamentals of Computing",
                    "target_block_id": block.id,
                    "anchor_key": "anc_unit_1",
                    "review_state": "ACCEPTED",
                    "metadata": {"custom_tag": "core_curriculum"}
                }
            ],
            edges=[]
        )
        db_session.add(snapshot)
        db_session.commit()

        builder = KnowledgeBuilder(db_session)
        version = builder.compile_snapshot(snapshot.id)

        assert version.status == "FINALIZED"
        entities = db_session.query(KnowledgeEntity).filter(KnowledgeEntity.knowledge_version_id == version.id).all()
        assert len(entities) == 1

        unit_entity = entities[0]
        assert unit_entity.entity_type == "UNIT"
        assert unit_entity.title == "Unit 1: Fundamentals of Computing"
        assert unit_entity.stable_id == "anc_unit_1"
        assert unit_entity.metadata_json.get("custom_tag") == "core_curriculum"
        assert unit_entity.metadata_json.get("canonical_source_position") == [1, 1]
        assert unit_entity.metadata_json.get("source_position_origin") == "DIRECT"

    def test_b_full_hierarchy_preservation(self, db_session):
        """B. Verify UNIT -> CHAPTER -> SECTION -> TOPIC -> CONCEPT retains complete 5-level structure and CONTAINS edges."""
        doc, page = create_test_document(db_session)
        b1 = create_block(db_session, doc, page, "b1", 1, 1, "Unit 1")
        b2 = create_block(db_session, doc, page, "b2", 1, 2, "Chapter 1")
        b3 = create_block(db_session, doc, page, "b3", 2, 1, "Section 1.1")
        b4 = create_block(db_session, doc, page, "b4", 2, 2, "Topic A")
        b5 = create_block(db_session, doc, page, "b5", 2, 3, "Concept Alpha")

        nodes = [
            {"node_id": "n_u", "category": "UNIT", "title": "Unit 1", "target_block_id": "b1", "anchor_key": "anc_u", "review_state": "ACCEPTED"},
            {"node_id": "n_c", "category": "CHAPTER", "title": "Chapter 1", "target_block_id": "b2", "anchor_key": "anc_c", "review_state": "ACCEPTED"},
            {"node_id": "n_s", "category": "SECTION", "title": "Section 1.1", "target_block_id": "b3", "anchor_key": "anc_s", "review_state": "ACCEPTED"},
            {"node_id": "n_t", "category": "TOPIC", "title": "Topic A", "target_block_id": "b4", "anchor_key": "anc_t", "review_state": "ACCEPTED"},
            {"node_id": "n_k", "category": "CONCEPT", "title": "Concept Alpha", "target_block_id": "b5", "anchor_key": "anc_k", "review_state": "ACCEPTED"},
        ]
        edges = [
            {"source_node_id": "n_u", "target_node_id": "n_c", "edge_type": "CONTAINS", "confidence": 1.0},
            {"source_node_id": "n_c", "target_node_id": "n_s", "edge_type": "CONTAINS", "confidence": 1.0},
            {"source_node_id": "n_s", "target_node_id": "n_t", "edge_type": "CONTAINS", "confidence": 1.0},
            {"source_node_id": "n_t", "target_node_id": "n_k", "edge_type": "CONTAINS", "confidence": 1.0},
        ]

        snapshot = AcademicGraphSnapshot(
            upload_id=doc.upload_id,
            pipeline_run_id="run_1",
            approval_version=1,
            approved_revision=1,
            base_graph_fingerprint="bfp_h",
            resolved_graph_fingerprint="rfp_h",
            approval_timestamp=time.time(),
            reviewer_id="reviewer_1",
            nodes=nodes,
            edges=edges
        )
        db_session.add(snapshot)
        db_session.commit()

        builder = KnowledgeBuilder(db_session)
        version = builder.compile_snapshot(snapshot.id)

        entities = db_session.query(KnowledgeEntity).filter(KnowledgeEntity.knowledge_version_id == version.id).all()
        assert len(entities) == 5
        types = {e.entity_type for e in entities}
        assert types == {"UNIT", "CHAPTER", "SECTION", "TOPIC", "CONCEPT"}

        # Verify all 4 CONTAINS relationships compiled
        rels = db_session.query(KnowledgeRelationship).filter(KnowledgeRelationship.knowledge_version_id == version.id).all()
        assert len(rels) == 4
        assert all(r.relationship_type == "CONTAINS" for r in rels)

    def test_c_chapter_only_identified_as_chapters_mode(self, db_session):
        """C. Chapter-only input remains chapters and get_selectable_containers identifies Chapters mode without inventing units."""
        doc, page = create_test_document(db_session)
        b1 = create_block(db_session, doc, page, "b_c1", 1, 1, "Chapter 1")
        b2 = create_block(db_session, doc, page, "b_sub1", 1, 5, "Subchapter 1.1")
        b3 = create_block(db_session, doc, page, "b_c2", 2, 1, "Chapter 2")

        nodes = [
            {"node_id": "n_c1", "category": "CHAPTER", "title": "Chapter 1: Intro", "target_block_id": "b_c1", "anchor_key": "anc_c1", "review_state": "ACCEPTED"},
            {"node_id": "n_sub1", "category": "CHAPTER", "title": "Subchapter 1.1: Background", "target_block_id": "b_sub1", "anchor_key": "anc_sub1", "review_state": "ACCEPTED"},
            {"node_id": "n_c2", "category": "CHAPTER", "title": "Chapter 2: Methods", "target_block_id": "b_c2", "anchor_key": "anc_c2", "review_state": "ACCEPTED"},
        ]
        edges = [
            # Subchapter 1.1 is nested inside Chapter 1
            {"source_node_id": "n_c1", "target_node_id": "n_sub1", "edge_type": "CONTAINS", "confidence": 1.0}
        ]

        snapshot = AcademicGraphSnapshot(
            upload_id=doc.upload_id,
            pipeline_run_id="run_1",
            approval_version=1,
            approved_revision=1,
            base_graph_fingerprint="bfp_c",
            resolved_graph_fingerprint="rfp_c",
            approval_timestamp=time.time(),
            reviewer_id="reviewer_1",
            nodes=nodes,
            edges=edges
        )
        db_session.add(snapshot)
        db_session.commit()

        builder = KnowledgeBuilder(db_session)
        version = builder.compile_snapshot(snapshot.id)

        result = get_selectable_containers(db_session, version.id)
        assert result.mode == SelectableContainerMode.CHAPTERS
        assert result.container_type == "CHAPTER"
        # Only top-level chapters (Chapter 1 and Chapter 2); Subchapter 1.1 is filtered out as nested child
        assert len(result.containers) == 2
        titles = [c.title for c in result.containers]
        assert titles == ["Chapter 1: Intro", "Chapter 2: Methods"]

    def test_d_no_usable_containers_review_required(self, db_session):
        """D. Input without usable containers (no units, no chapters) returns REVIEW_REQUIRED without manufacturing units."""
        doc, page = create_test_document(db_session)
        b1 = create_block(db_session, doc, page, "b_t1", 1, 1, "Topic 1")
        b2 = create_block(db_session, doc, page, "b_con1", 1, 2, "Concept 1")

        nodes = [
            {"node_id": "n_t1", "category": "TOPIC", "title": "Isolated Topic", "target_block_id": "b_t1", "anchor_key": "anc_t1", "review_state": "ACCEPTED"},
            {"node_id": "n_con1", "category": "CONCEPT", "title": "Isolated Concept", "target_block_id": "b_con1", "anchor_key": "anc_con1", "review_state": "ACCEPTED"},
        ]

        snapshot = AcademicGraphSnapshot(
            upload_id=doc.upload_id,
            pipeline_run_id="run_1",
            approval_version=1,
            approved_revision=1,
            base_graph_fingerprint="bfp_d",
            resolved_graph_fingerprint="rfp_d",
            approval_timestamp=time.time(),
            reviewer_id="reviewer_1",
            nodes=nodes,
            edges=[]
        )
        db_session.add(snapshot)
        db_session.commit()

        builder = KnowledgeBuilder(db_session)
        version = builder.compile_snapshot(snapshot.id)

        result = get_selectable_containers(db_session, version.id)
        assert result.mode == SelectableContainerMode.REVIEW_REQUIRED
        assert result.containers == []
        assert "review required" in result.message.lower()

    def test_e_out_of_order_uuids_and_shuffled_insertion_stable_ordering(self, db_session):
        """E. Out-of-order UUIDs and shuffled entity insertion do not change deterministic source ordering."""
        doc, page = create_test_document(db_session)
        create_block(db_session, doc, page, "b_p1_ro2", 1, 2)
        create_block(db_session, doc, page, "b_p1_ro5", 1, 5)
        create_block(db_session, doc, page, "b_p2_ro0", 2, 0)
        create_block(db_session, doc, page, "b_p3_ro1", 3, 1)

        # Shuffled nodes with arbitrary titles and positions
        nodes = [
            {"node_id": "node_4", "category": "TOPIC", "title": "Fourth in Source", "target_block_id": "b_p3_ro1", "anchor_key": "anc_4", "review_state": "ACCEPTED"},
            {"node_id": "node_2", "category": "TOPIC", "title": "Second in Source", "target_block_id": "b_p1_ro5", "anchor_key": "anc_2", "review_state": "ACCEPTED"},
            {"node_id": "node_1", "category": "TOPIC", "title": "First in Source", "target_block_id": "b_p1_ro2", "anchor_key": "anc_1", "review_state": "ACCEPTED"},
            {"node_id": "node_3", "category": "TOPIC", "title": "Third in Source", "target_block_id": "b_p2_ro0", "anchor_key": "anc_3", "review_state": "ACCEPTED"},
        ]

        snapshot = AcademicGraphSnapshot(
            upload_id=doc.upload_id,
            pipeline_run_id="run_1",
            approval_version=1,
            approved_revision=1,
            base_graph_fingerprint="bfp_e",
            resolved_graph_fingerprint="rfp_e",
            approval_timestamp=time.time(),
            reviewer_id="reviewer_1",
            nodes=nodes,
            edges=[]
        )
        db_session.add(snapshot)
        db_session.commit()

        builder = KnowledgeBuilder(db_session)
        version = builder.compile_snapshot(snapshot.id)

        entities = db_session.query(KnowledgeEntity).filter(KnowledgeEntity.knowledge_version_id == version.id).all()
        sorted_entities = sort_entities_by_source_order(entities)

        expected_titles = [
            "First in Source",   # (1, 2)
            "Second in Source",  # (1, 5)
            "Third in Source",   # (2, 0)
            "Fourth in Source",  # (3, 1)
        ]
        assert [e.title for e in sorted_entities] == expected_titles

    def test_f_multiple_source_positions_uses_earliest_actual_tuple(self):
        """F. Multiple source positions resolve to the lexicographically earliest actual tuple."""
        # Case 1: Standard comparison
        positions = [(2, 10), (1, 5), (1, 12)]
        assert compute_canonical_source_position(positions) == (1, 5)

        # Case 2: Preserves valid 0 value without truthiness loss
        positions_with_zero = [(1, 1), (1, 0), (2, 0)]
        assert compute_canonical_source_position(positions_with_zero) == (1, 0)

        # Case 3: Does NOT mix min page and min reading order independently
        # Block A is (page 2, ro 0). Block B is (page 1, ro 10).
        # Correct min tuple is (1, 10), NOT an invented (1, 0)!
        positions_no_mixing = [(2, 0), (1, 10)]
        assert compute_canonical_source_position(positions_no_mixing) == (1, 10)

        # Case 4: None filtering
        positions_with_none = [(None, 5), (3, None), (2, 4)]
        assert compute_canonical_source_position(positions_with_none) == (2, 4)

    def test_g_missing_positions_and_manual_containers_fallback(self, db_session):
        """G. Missing positions and manual containers follow descendant-derived fallback or documented fallback."""
        doc, page = create_test_document(db_session)
        # Block for child only
        create_block(db_session, doc, page, "b_child", 4, 2, "Child content")

        nodes = [
            # Manual container with no direct block, but containing a positioned child
            {"node_id": "u_manual", "category": "UNIT", "title": "Manual Unit", "target_block_id": None, "anchor_key": "anc_u_man", "review_state": "MODIFIED", "metadata": {"provenance": "HUMAN_OVERRIDE"}},
            {"node_id": "t_child", "category": "TOPIC", "title": "Positioned Child", "target_block_id": "b_child", "anchor_key": "anc_t_child", "review_state": "ACCEPTED"},
            # Isolated manual node with no block and no positioned children
            {"node_id": "t_isolated", "category": "TOPIC", "title": "Isolated Manual Topic", "target_block_id": None, "anchor_key": "anc_t_iso", "review_state": "MODIFIED", "metadata": {"provenance": "HUMAN_OVERRIDE"}},
        ]
        edges = [
            {"source_node_id": "u_manual", "target_node_id": "t_child", "edge_type": "CONTAINS", "confidence": 1.0}
        ]

        snapshot = AcademicGraphSnapshot(
            upload_id=doc.upload_id,
            pipeline_run_id="run_1",
            approval_version=1,
            approved_revision=1,
            base_graph_fingerprint="bfp_g",
            resolved_graph_fingerprint="rfp_g",
            approval_timestamp=time.time(),
            reviewer_id="reviewer_1",
            nodes=nodes,
            edges=edges
        )
        db_session.add(snapshot)
        db_session.commit()

        builder = KnowledgeBuilder(db_session)
        version = builder.compile_snapshot(snapshot.id)

        entities = {e.stable_id: e for e in db_session.query(KnowledgeEntity).filter(KnowledgeEntity.knowledge_version_id == version.id).all()}

        # 1. Manual container derives position from descendant child
        u_ent = entities["anc_u_man"]
        assert u_ent.metadata_json.get("canonical_source_position") == [4, 2]
        assert u_ent.metadata_json.get("source_position_origin") == "DESCENDANT_DERIVED"
        assert u_ent.metadata_json.get("source_position_descendant_id") == "t_child"
        # Verify no dummy evidence row was invented for the manual container
        u_ev = db_session.query(KnowledgeEvidence).filter(KnowledgeEvidence.entity_id == u_ent.id).all()
        assert len(u_ev) == 0

        # 2. Isolated node has FALLBACK origin and None position
        iso_ent = entities["anc_t_iso"]
        assert iso_ent.metadata_json.get("canonical_source_position") is None
        assert iso_ent.metadata_json.get("source_position_origin") == "FALLBACK"

        # 3. In sorting, positioned entities precede fallback entities
        all_sorted = sort_entities_by_source_order(list(entities.values()))
        assert all_sorted[-1].stable_id == "anc_t_iso"

    def test_h_evidence_preserves_correct_document_ids_and_provenance(self, db_session):
        """H. Evidence records point to Document.id (not upload_id), preserving page number and provenance."""
        distinct_upload_id = f"upload-spec-{uuid.uuid4()}"
        distinct_doc_id = f"doc-spec-{uuid.uuid4()}"
        doc, page = create_test_document(db_session, upload_id=distinct_upload_id, doc_id=distinct_doc_id)

        block = create_block(db_session, doc, page, "b_spec_1", page_number=7, reading_order=3, text="Special Evidence Block")

        snapshot = AcademicGraphSnapshot(
            upload_id=distinct_upload_id,
            pipeline_run_id="run_1",
            approval_version=1,
            approved_revision=1,
            base_graph_fingerprint="bfp_h",
            resolved_graph_fingerprint="rfp_h",
            approval_timestamp=time.time(),
            reviewer_id="reviewer_1",
            nodes=[
                {"node_id": "n1", "category": "CONCEPT", "title": "Concept H", "target_block_id": block.id, "anchor_key": "anc_h", "review_state": "ACCEPTED"}
            ],
            edges=[]
        )
        db_session.add(snapshot)
        db_session.commit()

        builder = KnowledgeBuilder(db_session)
        version = builder.compile_snapshot(snapshot.id)

        evidence = db_session.query(KnowledgeEvidence).filter(KnowledgeEvidence.source_anchor_key == "anc_h").first()
        assert evidence is not None
        # Must be Document.id, NOT upload_id
        assert evidence.document_id == distinct_doc_id
        assert evidence.document_id != distinct_upload_id
        assert evidence.page_number == 7
        assert evidence.text_reference == "Special Evidence Block"
        assert evidence.provenance == KnowledgeEvidenceProvenance.EXPLICIT_CLASSIFIER.value

    def test_i_compiling_same_snapshot_twice_remains_idempotent(self, db_session):
        """I. Compiling the same snapshot twice is idempotent and returns the existing finalized version."""
        doc, page = create_test_document(db_session)
        create_block(db_session, doc, page, "b_idem", 1, 1)

        snapshot = AcademicGraphSnapshot(
            upload_id=doc.upload_id,
            pipeline_run_id="run_1",
            approval_version=1,
            approved_revision=1,
            base_graph_fingerprint="bfp_i",
            resolved_graph_fingerprint="rfp_i",
            approval_timestamp=time.time(),
            reviewer_id="reviewer_1",
            nodes=[
                {"node_id": "n_idem", "category": "TOPIC", "title": "Idempotent Topic", "target_block_id": "b_idem", "anchor_key": "anc_idem", "review_state": "ACCEPTED"}
            ],
            edges=[]
        )
        db_session.add(snapshot)
        db_session.commit()

        builder = KnowledgeBuilder(db_session)
        v1 = builder.compile_snapshot(snapshot.id)
        v2 = builder.compile_snapshot(snapshot.id)

        assert v1.id == v2.id
        total_versions = db_session.query(KnowledgeVersion).filter(KnowledgeVersion.snapshot_id == snapshot.id).count()
        assert total_versions == 1

    def test_j_reapproval_creates_new_version_preserving_history(self, db_session):
        """J. Re-approval creates new snapshot and version identities while prior finalized version and entities remain unchanged."""
        doc, page = create_test_document(db_session)
        create_block(db_session, doc, page, "b_v1", 1, 1, "V1 Topic")
        create_block(db_session, doc, page, "b_v2", 1, 2, "V2 Added Topic")

        # Snapshot v1
        snap_v1 = AcademicGraphSnapshot(
            upload_id=doc.upload_id,
            pipeline_run_id="run_1",
            approval_version=1,
            approved_revision=1,
            base_graph_fingerprint="bfp_v1",
            resolved_graph_fingerprint="rfp_v1",
            approval_timestamp=time.time(),
            reviewer_id="reviewer_1",
            nodes=[
                {"node_id": "n1", "category": "TOPIC", "title": "Topic Original", "target_block_id": "b_v1", "anchor_key": "anc_v1", "review_state": "ACCEPTED"}
            ],
            edges=[]
        )
        db_session.add(snap_v1)
        db_session.commit()

        builder = KnowledgeBuilder(db_session)
        v1 = builder.compile_snapshot(snap_v1.id)

        # Snapshot v2 (Re-approval with new node)
        snap_v2 = AcademicGraphSnapshot(
            upload_id=doc.upload_id,
            pipeline_run_id="run_1",
            approval_version=2,
            approved_revision=2,
            base_graph_fingerprint="bfp_v2",
            resolved_graph_fingerprint="rfp_v2",
            approval_timestamp=time.time() + 10,
            reviewer_id="reviewer_2",
            nodes=[
                {"node_id": "n1", "category": "TOPIC", "title": "Topic Original", "target_block_id": "b_v1", "anchor_key": "anc_v1", "review_state": "ACCEPTED"},
                {"node_id": "n2", "category": "TOPIC", "title": "Topic Added in V2", "target_block_id": "b_v2", "anchor_key": "anc_v2", "review_state": "ACCEPTED"}
            ],
            edges=[]
        )
        db_session.add(snap_v2)
        db_session.commit()

        v2 = builder.compile_snapshot(snap_v2.id)

        # Verify distinct identities
        assert v1.id != v2.id
        assert v1.snapshot_id == snap_v1.id
        assert v2.snapshot_id == snap_v2.id

        # Verify v1 entities are strictly preserved
        v1_entities = db_session.query(KnowledgeEntity).filter(KnowledgeEntity.knowledge_version_id == v1.id).all()
        assert len(v1_entities) == 1
        assert v1_entities[0].title == "Topic Original"

        # Verify v2 entities include added node
        v2_entities = db_session.query(KnowledgeEntity).filter(KnowledgeEntity.knowledge_version_id == v2.id).all()
        assert len(v2_entities) == 2

        # Verify KnowledgeRepository resolves v2 as latest finalized version
        repo = KnowledgeRepository(db_session)
        latest = repo.get_latest_finalized_version(doc.id)
        assert latest is not None
        assert latest.id == v2.id

        # Verify list_finalized_versions returns [v2, v1] in descending approval version order
        all_versions = repo.list_finalized_versions(doc.id)
        assert [v.id for v in all_versions] == [v2.id, v1.id]

    def test_k_immutability_protections_reject_prohibited_changes(self, db_session):
        """K. Existing immutability triggers block mutations or deletions on finalized knowledge versions and entities."""
        doc, page = create_test_document(db_session)
        create_block(db_session, doc, page, "b_imm", 1, 1)

        snapshot = AcademicGraphSnapshot(
            upload_id=doc.upload_id,
            pipeline_run_id="run_1",
            approval_version=1,
            approved_revision=1,
            base_graph_fingerprint="bfp_k",
            resolved_graph_fingerprint="rfp_k",
            approval_timestamp=time.time(),
            reviewer_id="reviewer_1",
            nodes=[
                {"node_id": "n_k", "category": "CONCEPT", "title": "Immutable Concept", "target_block_id": "b_imm", "anchor_key": "anc_k", "review_state": "ACCEPTED"}
            ],
            edges=[]
        )
        db_session.add(snapshot)
        db_session.commit()

        builder = KnowledgeBuilder(db_session)
        version = builder.compile_snapshot(snapshot.id)
        assert version.status == "FINALIZED"

        entity = db_session.query(KnowledgeEntity).filter(KnowledgeEntity.knowledge_version_id == version.id).first()

        # 1. Attempting to mutate entity title under finalized version must fail
        entity.title = "Illegal Title Mutation"
        with pytest.raises((ValueError, OperationalError, IntegrityError)):
            db_session.commit()
        db_session.rollback()

        # 2. Attempting to delete finalized version must fail
        db_session.delete(version)
        with pytest.raises((ValueError, OperationalError, IntegrityError)):
            db_session.commit()
        db_session.rollback()
