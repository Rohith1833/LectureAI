"""
Phase 3 Integration Test Suite:
Exact selected-container scope, consistent planner/validator selection,
correct retrieval identifiers, and substantive textbook content.
"""

import uuid
import time
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.document import Base, Document, DocumentPage, DocumentBlock
from app.models.review import AcademicGraphSnapshot
from app.models.knowledge import KnowledgeVersion, KnowledgeEntity, KnowledgeRelationship, KnowledgeEvidence
from app.models.artifact import ArtifactJob
from app.services.intelligence.knowledge_builder import KnowledgeBuilder
from app.services.intelligence.knowledge_ordering import (
    SelectableContainerMode,
    get_selectable_containers,
    sort_entities_by_source_order
)
from app.services.artifact.selection_resolver import (
    resolve_effective_selection,
    resolve_effective_selection_for_job,
    resolve_document_id_for_version,
    EffectiveSelection
)
from app.services.artifact.artifact_service import ArtifactService
from app.services.artifact.artifact_planner import ArtifactPlanner
from app.services.artifact.artifact_validator import ArtifactValidator, ArtifactValidationContext
from app.schemas.artifact import ArtifactJobCreate, ArtifactJobRead, ArtifactType, SlideModel, SlideType, ArtifactPlan, ArtifactGenerationConfig
from app.services.retrieval.retrieval_service import RetrievalService
from app.services.retrieval.passage_retriever import PassageRetriever, PassageCandidate
from app.services.retrieval.evidence_retriever import EvidenceCandidate
from app.services.retrieval.scope_resolver import ResolvedScope
from app.schemas.retrieval import RetrievalScope, RetrievalRequest, RetrievalOptions
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.document_repository import DocumentRepository
from app.services.retrieval.ranker import RankingWeights
from app.services.generation.base import LLMProvider, LLMGenerationRequest, LLMGenerationResponse
from app.services.generation.errors import GroundingValidationError
from fastapi import HTTPException
from pydantic import ValidationError


class CapturingLLMProvider(LLMProvider):
    """Test fixture provider that captures requests and returns valid schema slides."""
    def __init__(self):
        self.captured_requests = []

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
        self.captured_requests.append(request)
        # Extract supplied source_node_ids and evidence_ids from prompt
        import re
        node_ids = re.findall(r"\((\S+?)\)", request.prompt)
        ev_ids = re.findall(r"\[Evidence ID: (\S+?)\]", request.prompt)
        
        slide_node = node_ids[0] if node_ids else "dummy_node"
        slide_ev = [ev_ids[0]] if ev_ids else []

        mock_slides = {
            "slides": [
                {
                    "slide_type": "CONTENT",
                    "title": "Captured Presentation Slide",
                    "content": ["Explanation grounded in context."],
                    "speaker_notes": "Notes",
                    "source_node_ids": [slide_node],
                    "evidence_ids": slide_ev
                }
            ]
        }
        return LLMGenerationResponse(
            raw_response="",
            structured_output=mock_slides,
            model_name="capturing-test-provider"
        )


@pytest.fixture
def four_unit_db():
    """
    Sets up a complete isolated SQLite database with:
    - Distinct Document.id and upload_id (doc_id != upload_id)
    - 4 Units with UUIDs inversely ordered from textbook order
    - UNIT -> CHAPTER -> SECTION -> TOPIC -> CONCEPT hierarchy in Unit 2
    - Same page sharing between Unit 1 and Unit 2 (Page 2)
    - Shared descendant (Concept) between Unit 2 and Unit 3
    - Substantive textbook blocks and passages with distinct markers
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # 1. Document with distinct doc_id and upload_id
    doc_id = "doc_alpha_textbook_99"
    upload_id = "upl_beta_upload_42"
    doc = Document(
        id=doc_id,
        upload_id=upload_id,
        status="processed",
        review_state="APPROVED",
        extraction_timestamp="2026-09-28T21:00:00",
        processing_time=1.23
    )
    db.add(doc)
    db.flush()

    # Pages 1 to 5
    for p_num in range(1, 6):
        db.add(DocumentPage(
            id=f"page_{p_num}",
            document_id=doc_id,
            page_number=p_num,
            width=612.0,
            height=792.0
        ))

    # Blocks with substantive explanations and unique markers
    # Page 1: Unit 1
    blk_u1 = DocumentBlock(
        id="blk_u1", document_id=doc_id, page_id="page_1", page_number=1, reading_order=0,
        block_type="PARAGRAPH", text="MARKER_UNIT_1_EXCLUSIVE: Introduction to Boolean Logic and Gates.",
        x0=50.0, y0=50.0, x1=500.0, y1=150.0
    )
    # Page 2: SHARED PAGE between Unit 1 and Unit 2
    blk_u1_p2 = DocumentBlock(
        id="blk_u1_p2", document_id=doc_id, page_id="page_2", page_number=2, reading_order=0,
        block_type="PARAGRAPH", text="MARKER_UNIT_1_SAME_PAGE: Unit 1 combinational circuits on shared page 2.",
        x0=50.0, y0=50.0, x1=500.0, y1=150.0
    )
    blk_u2_p2 = DocumentBlock(
        id="blk_u2_p2", document_id=doc_id, page_id="page_2", page_number=2, reading_order=10,
        block_type="PARAGRAPH", text="MARKER_UNIT_2_EXCLUSIVE: Unit 2 register transfer and processor design on shared page 2.",
        x0=50.0, y0=200.0, x1=500.0, y1=300.0
    )
    # Page 3: Unit 2 Deep Hierarchy & Shared Concept
    blk_u2_ch = DocumentBlock(
        id="blk_u2_ch", document_id=doc_id, page_id="page_3", page_number=3, reading_order=0,
        block_type="PARAGRAPH", text="Unit 2 Chapter on Memory Hierarchy.",
        x0=50.0, y0=50.0, x1=500.0, y1=100.0
    )
    blk_shared = DocumentBlock(
        id="blk_shared", document_id=doc_id, page_id="page_3", page_number=3, reading_order=10,
        block_type="PARAGRAPH", text="MARKER_SHARED_CONCEPT: Pipeline synchronization shared across Units 2 and 3.",
        x0=50.0, y0=150.0, x1=500.0, y1=250.0
    )
    # Page 4: Unit 3 Exclusive
    blk_u3 = DocumentBlock(
        id="blk_u3", document_id=doc_id, page_id="page_4", page_number=4, reading_order=0,
        block_type="PARAGRAPH", text="MARKER_UNIT_3_EXCLUSIVE: Unit 3 Operating System Processes.",
        x0=50.0, y0=50.0, x1=500.0, y1=200.0
    )
    # Page 5: Unit 4 Exclusive
    blk_u4 = DocumentBlock(
        id="blk_u4", document_id=doc_id, page_id="page_5", page_number=5, reading_order=0,
        block_type="PARAGRAPH", text="MARKER_UNIT_4_EXCLUSIVE: Unit 4 Distributed Protocols and Consensus.",
        x0=50.0, y0=50.0, x1=500.0, y1=200.0
    )
    db.add_all([blk_u1, blk_u1_p2, blk_u2_p2, blk_u2_ch, blk_shared, blk_u3, blk_u4])
    db.flush()

    # 2. Approved Snapshot Nodes:
    # Intentionally use reverse UUIDs so UUID order != textbook reading order!
    # Unit 1: "uuid_4_unit1" (reading order on Page 1)
    # Unit 2: "uuid_3_unit2" (reading order on Page 2)
    # Unit 3: "uuid_2_unit3" (reading order on Page 4)
    # Unit 4: "uuid_1_unit4" (reading order on Page 5)
    nodes = [
        {"node_id": "uuid_4_unit1", "category": "UNIT", "title": "Unit 1: Logic Gates", "anchor_key": "u1", "target_block_id": "blk_u1"},
        {"node_id": "node_t1", "category": "TOPIC", "title": "Topic 1.1: Boolean Algebra", "anchor_key": "t1", "target_block_id": "blk_u1_p2"},

        {"node_id": "uuid_3_unit2", "category": "UNIT", "title": "Unit 2: Processor Architecture", "anchor_key": "u2", "target_block_id": "blk_u2_p2"},
        {"node_id": "node_c2", "category": "CHAPTER", "title": "Chapter 2: Memory", "anchor_key": "c2", "target_block_id": "blk_u2_ch"},
        {"node_id": "node_s2", "category": "SECTION", "title": "Section 2.1: Cache", "anchor_key": "s2", "target_block_id": None},
        {"node_id": "node_t2", "category": "TOPIC", "title": "Topic 2.1.1: Cache Lines", "anchor_key": "t2", "target_block_id": None},
        {"node_id": "node_cp2", "category": "CONCEPT", "title": "Concept 2.1.1.1: Cache Misses", "anchor_key": "cp2", "target_block_id": "blk_u2_ch"},
        {"node_id": "node_cp_shared", "category": "CONCEPT", "title": "Shared Pipeline Concept", "anchor_key": "cp_shared", "target_block_id": "blk_shared"},

        {"node_id": "uuid_2_unit3", "category": "UNIT", "title": "Unit 3: Operating Systems", "anchor_key": "u3", "target_block_id": "blk_u3"},
        {"node_id": "node_t3", "category": "TOPIC", "title": "Topic 3.1: Kernel Scheduling", "anchor_key": "t3", "target_block_id": "blk_u3"},

        {"node_id": "uuid_1_unit4", "category": "UNIT", "title": "Unit 4: Distributed Systems", "anchor_key": "u4", "target_block_id": "blk_u4"},
        {"node_id": "node_t4", "category": "TOPIC", "title": "Topic 4.1: Raft Consensus", "anchor_key": "t4", "target_block_id": "blk_u4"},
    ]

    edges = [
        # Unit 1 hierarchy
        {"source_node_id": "uuid_4_unit1", "target_node_id": "node_t1", "edge_type": "CONTAINS"},
        # Unit 2 deep hierarchy: UNIT -> CHAPTER -> SECTION -> TOPIC -> CONCEPT
        {"source_node_id": "uuid_3_unit2", "target_node_id": "node_c2", "edge_type": "CONTAINS"},
        {"source_node_id": "node_c2", "target_node_id": "node_s2", "edge_type": "CONTAINS"},
        {"source_node_id": "node_s2", "target_node_id": "node_t2", "edge_type": "CONTAINS"},
        {"source_node_id": "node_t2", "target_node_id": "node_cp2", "edge_type": "CONTAINS"},
        {"source_node_id": "node_t2", "target_node_id": "node_cp_shared", "edge_type": "CONTAINS"},
        # Unit 3 shares the same concept
        {"source_node_id": "uuid_2_unit3", "target_node_id": "node_t3", "edge_type": "CONTAINS"},
        {"source_node_id": "node_t3", "target_node_id": "node_cp_shared", "edge_type": "CONTAINS"},
        # Unit 4
        {"source_node_id": "uuid_1_unit4", "target_node_id": "node_t4", "edge_type": "CONTAINS"},
    ]

    snap = AcademicGraphSnapshot(
        id="snap_4units_v1",
        upload_id=upload_id,
        pipeline_run_id="run_1",
        approval_version=1,
        approved_revision=1,
        base_graph_fingerprint="base_fp",
        resolved_graph_fingerprint="res_fp",
        approval_timestamp=time.time(),
        reviewer_id="rev_1",
        nodes=nodes,
        edges=edges
    )
    db.add(snap)
    db.commit()

    # Compile into finalized KnowledgeVersion
    builder = KnowledgeBuilder(db)
    kv = builder.compile_snapshot(snap.id)
    assert kv.status == "FINALIZED"

    # Map unit titles to compiled entity IDs
    compiled_entities = db.query(KnowledgeEntity).filter(KnowledgeEntity.knowledge_version_id == kv.id).all()
    unit_map = {e.title.split(":")[0].strip(): e for e in compiled_entities if e.entity_type == "UNIT"}

    yield {
        "db": db,
        "doc": doc,
        "version": kv,
        "unit_map": unit_map,
        "all_entities": {e.title: e for e in compiled_entities}
    }
    db.close()


def test_effective_selection_order_preservation(four_unit_db):
    """
    Assert:
    - Input selection in reverse order [Unit 4, Unit 2] preserves textbook order [Unit 2, Unit 4].
    - Saved configuration persists that exact selection.
    """
    db = four_unit_db["db"]
    doc = four_unit_db["doc"]
    kv = four_unit_db["version"]
    u_map = four_unit_db["unit_map"]

    u2 = u_map["Unit 2"]
    u4 = u_map["Unit 4"]

    service = ArtifactService(db)
    req = ArtifactJobCreate(
        upload_id=doc.upload_id,
        knowledge_version_id=kv.id,
        artifact_type=ArtifactType.PPTX,
        config={"selected_unit_ids": [u4.id, u2.id]} # Provided in REVERSE order
    )

    job_read = service.create_artifact_job(req)
    assert job_read.status.value == "PENDING"

    # Verify persisted config has textbook canonical order: Unit 2, then Unit 4
    persisted_ids = job_read.config["selected_unit_ids"]
    assert persisted_ids == [u2.id, u4.id]
    assert job_read.config["container_mode"] == "UNITS"
    assert job_read.config["container_type"] == "UNIT"
    assert job_read.config["document_id"] == doc.id


@pytest.mark.asyncio
async def test_scope_enforcement_and_substantive_retrieval(four_unit_db):
    """
    Assert:
    - Both units' relevant descendants reach planning context.
    - Unique Unit 1 and Unit 3 markers DO NOT reach planning context.
    - Substantive textbook passages reach the planning context.
    - Real ScopeResolver receives Document.id (not upload_id).
    """
    db = four_unit_db["db"]
    doc = four_unit_db["doc"]
    kv = four_unit_db["version"]
    u_map = four_unit_db["unit_map"]

    u2 = u_map["Unit 2"]
    u4 = u_map["Unit 4"]

    capturing_provider = CapturingLLMProvider()
    knowledge_repo = KnowledgeRepository(db)
    document_repo = DocumentRepository(db)
    retrieval_service = RetrievalService(knowledge_repo, document_repo)

    planner = ArtifactPlanner(knowledge_repo, retrieval_service, capturing_provider)

    job = ArtifactJob(
        id=str(uuid.uuid4()),
        upload_id=doc.upload_id,
        knowledge_version_id=kv.id,
        artifact_type="PPTX",
        status="PLANNING",
        config={
            "selected_unit_ids": [u2.id, u4.id],
            "document_id": doc.id
        }
    )
    db.add(job)
    db.commit()

    plan = await planner.plan(ArtifactJobRead.model_validate(job))
    assert len(plan.slides) > 0

    # Inspect captured LLM prompts
    all_prompt_text = " ".join([r.prompt for r in capturing_provider.captured_requests])

    # 1. Substantive content for selected units MUST be present
    assert "MARKER_UNIT_2_EXCLUSIVE" in all_prompt_text
    assert "MARKER_UNIT_4_EXCLUSIVE" in all_prompt_text
    # 2. Shared descendant reachable from Unit 2 MUST be present
    assert "MARKER_SHARED_CONCEPT" in all_prompt_text

    # 3. Unselected units' exclusive content MUST NOT be present
    assert "MARKER_UNIT_1_EXCLUSIVE" not in all_prompt_text
    assert "MARKER_UNIT_1_SAME_PAGE" not in all_prompt_text
    assert "MARKER_UNIT_3_EXCLUSIVE" not in all_prompt_text


def test_validator_expects_exact_selected_containers(four_unit_db):
    """
    Assert:
    - Validator expects exactly the selected containers (Unit 2 and Unit 4).
    - Unselected units (Unit 1, Unit 3) are not expected.
    - Out-of-scope references are rejected with GROUNDING error.
    - Missing selected unit is rejected with COVERAGE error.
    """
    db = four_unit_db["db"]
    doc = four_unit_db["doc"]
    kv = four_unit_db["version"]
    u_map = four_unit_db["unit_map"]
    all_ents = four_unit_db["all_entities"]

    u1 = u_map["Unit 1"]
    u2 = u_map["Unit 2"]
    u4 = u_map["Unit 4"]

    selection = resolve_effective_selection(
        db=db,
        version_id=kv.id,
        upload_id=doc.upload_id,
        config={"selected_unit_ids": [u2.id, u4.id]}
    )

    validator = ArtifactValidator()
    context = ArtifactValidationContext(
        valid_node_ids=selection.permitted_entity_ids,
        valid_evidence_ids=selection.permitted_evidence_ids,
        expected_units=set(selection.selected_container_ids),
        config={},
        container_type=selection.container_type,
        container_to_descendants=selection.container_to_descendants
    )

    # Valid plan covering Unit 2 and Unit 4
    valid_plan = ArtifactPlan(slides=[
        SlideModel(slide_type=SlideType.TITLE, title="Title", content=[], source_node_ids=[u2.id]),
        SlideModel(slide_type=SlideType.CONTENT, title="Unit 2 Slide", content=["Bullet"], source_node_ids=[u2.id]),
        SlideModel(slide_type=SlideType.CONTENT, title="Unit 4 Slide", content=["Bullet"], source_node_ids=[u4.id])
    ])
    res = validator.validate(valid_plan, context)
    assert res.is_valid is True

    # Missing Unit 4 -> COVERAGE failure
    missing_unit_plan = ArtifactPlan(slides=[
        SlideModel(slide_type=SlideType.TITLE, title="Title", content=[], source_node_ids=[u2.id]),
        SlideModel(slide_type=SlideType.CONTENT, title="Unit 2 Only", content=["Bullet"], source_node_ids=[u2.id])
    ])
    res_cov = validator.validate(missing_unit_plan, context)
    assert res_cov.is_valid is False
    assert any(e.category == "COVERAGE" and u4.id in e.message for e in res_cov.errors)

    # Citing unselected Unit 1 -> GROUNDING failure
    out_of_scope_plan = ArtifactPlan(slides=[
        SlideModel(slide_type=SlideType.TITLE, title="Title", content=[], source_node_ids=[u2.id]),
        SlideModel(slide_type=SlideType.CONTENT, title="Unit 2", content=["Bullet"], source_node_ids=[u2.id]),
        SlideModel(slide_type=SlideType.CONTENT, title="Unit 4", content=["Bullet"], source_node_ids=[u4.id]),
        SlideModel(slide_type=SlideType.CONTENT, title="Unit 1 Leak", content=["Bullet"], source_node_ids=[u1.id])
    ])
    res_ground = validator.validate(out_of_scope_plan, context)
    assert res_ground.is_valid is False
    assert any(e.category == "GROUNDING" and u1.id in e.message for e in res_ground.errors)


def test_invalid_requests_rejected(four_unit_db):
    """
    Assert:
    - Rejects both selected_unit_ids and num_units simultaneously.
    - Rejects empty selected_unit_ids.
    - Rejects foreign-version or non-container IDs.
    - Normalizes duplicates.
    """
    db = four_unit_db["db"]
    doc = four_unit_db["doc"]
    kv = four_unit_db["version"]
    u_map = four_unit_db["unit_map"]
    all_ents = four_unit_db["all_entities"]

    u2 = u_map["Unit 2"]
    concept_entity = all_ents["Concept 2.1.1.1: Cache Misses"]

    service = ArtifactService(db)

    # 1. Both selected_unit_ids and num_units
    with pytest.raises((HTTPException, ValidationError)):
        service.create_artifact_job(ArtifactJobCreate(
            upload_id=doc.upload_id,
            knowledge_version_id=kv.id,
            config={"selected_unit_ids": [u2.id], "num_units": 1}
        ))

    # 2. Empty selection
    with pytest.raises((HTTPException, ValidationError)):
        service.create_artifact_job(ArtifactJobCreate(
            upload_id=doc.upload_id,
            knowledge_version_id=kv.id,
            config={"selected_unit_ids": []}
        ))

    # 3. Non-container entity (Concept selected as container)
    with pytest.raises(HTTPException) as exc3:
        service.create_artifact_job(ArtifactJobCreate(
            upload_id=doc.upload_id,
            knowledge_version_id=kv.id,
            config={"selected_unit_ids": [concept_entity.id]}
        ))
    assert "cannot be selected as a top-level unit container" in exc3.value.detail

    # 4. Foreign/Unknown ID
    with pytest.raises(HTTPException) as exc4:
        service.create_artifact_job(ArtifactJobCreate(
            upload_id=doc.upload_id,
            knowledge_version_id=kv.id,
            config={"selected_unit_ids": ["non_existent_uuid"]}
        ))
    assert "not found" in exc4.value.detail

    # 5. Duplicates are normalized
    job_dup = service.create_artifact_job(ArtifactJobCreate(
        upload_id=doc.upload_id,
        knowledge_version_id=kv.id,
        config={"selected_unit_ids": [u2.id, u2.id]}
    ))
    assert job_dup.config["selected_unit_ids"] == [u2.id]


def test_legacy_num_units_and_default_behavior(four_unit_db):
    """
    Assert:
    - num_units resolves the first N containers in textbook canonical order.
    - Invalid N (<= 0 or > count) is rejected.
    - Omitting both fields defaults to all containers in textbook canonical order.
    """
    db = four_unit_db["db"]
    doc = four_unit_db["doc"]
    kv = four_unit_db["version"]
    u_map = four_unit_db["unit_map"]

    u1 = u_map["Unit 1"]
    u2 = u_map["Unit 2"]
    u3 = u_map["Unit 3"]
    u4 = u_map["Unit 4"]

    service = ArtifactService(db)

    # 1. num_units = 2 -> selects Unit 1, Unit 2 (textbook order)
    job_n2 = service.create_artifact_job(ArtifactJobCreate(
        upload_id=doc.upload_id,
        knowledge_version_id=kv.id,
        config={"num_units": 2}
    ))
    assert job_n2.config["selected_unit_ids"] == [u1.id, u2.id]

    # 2. num_units = 0 rejected
    with pytest.raises((HTTPException, ValidationError)):
        service.create_artifact_job(ArtifactJobCreate(
            upload_id=doc.upload_id,
            knowledge_version_id=kv.id,
            config={"num_units": 0}
        ))

    # 3. num_units = 10 (> 4) rejected
    with pytest.raises(HTTPException) as exc_over:
        service.create_artifact_job(ArtifactJobCreate(
            upload_id=doc.upload_id,
            knowledge_version_id=kv.id,
            config={"num_units": 10}
        ))
    assert "exceeds available" in exc_over.value.detail

    # 4. Neither field supplied -> defaults to all 4 units in textbook order
    job_all = service.create_artifact_job(ArtifactJobCreate(
        upload_id=doc.upload_id,
        knowledge_version_id=kv.id,
        config={}
    ))
    assert job_all.config["selected_unit_ids"] == [u1.id, u2.id, u3.id, u4.id]


def test_chapters_mode_selection_and_coverage():
    """
    Assert:
    - When no units exist, system detects Chapters mode.
    - Top-level chapters serve as selectable containers.
    - Validator reports missing chapters using chapter label.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    doc = Document(id="doc_ch_1", upload_id="upl_ch_1", status="processed", review_state="APPROVED", extraction_timestamp="now", processing_time=1.0)
    db.add(doc)
    db.flush()

    nodes = [
        {"node_id": "ch1", "category": "CHAPTER", "title": "Chapter 1: Foundations", "anchor_key": "c1"},
        {"node_id": "ch2", "category": "CHAPTER", "title": "Chapter 2: Advanced", "anchor_key": "c2"},
        {"node_id": "sub_ch2_1", "category": "CHAPTER", "title": "Chapter 2.1: Nested", "anchor_key": "c2_1"},
    ]
    edges = [
        {"source_node_id": "ch2", "target_node_id": "sub_ch2_1", "edge_type": "CONTAINS"}
    ]
    snap = AcademicGraphSnapshot(
        id="snap_ch", upload_id=doc.upload_id, pipeline_run_id="p1", approval_version=1,
        approved_revision=1, base_graph_fingerprint="b", resolved_graph_fingerprint="r",
        approval_timestamp=time.time(), reviewer_id="rev", nodes=nodes, edges=edges
    )
    db.add(snap)
    db.commit()

    kv = KnowledgeBuilder(db).compile_snapshot(snap.id)

    # Resolve selectable containers
    res = get_selectable_containers(db, kv.id)
    assert res.mode == SelectableContainerMode.CHAPTERS
    assert res.container_type == "CHAPTER"
    # Nested sub_ch2_1 must be excluded from top-level chapters!
    top_titles = [c.title for c in res.containers]
    assert "Chapter 1: Foundations" in top_titles
    assert "Chapter 2: Advanced" in top_titles
    assert "Chapter 2.1: Nested" not in top_titles

    # Selection resolution in Chapters mode
    sel = resolve_effective_selection(db, kv.id, doc.upload_id, {"selected_unit_ids": [res.containers[0].id]})
    assert sel.container_mode == SelectableContainerMode.CHAPTERS
    assert sel.container_type == "CHAPTER"
    assert len(sel.selected_container_ids) == 1

    # Validator coverage error mentions chapter
    val = ArtifactValidator()
    ctx = ArtifactValidationContext(
        valid_node_ids=sel.permitted_entity_ids,
        valid_evidence_ids=sel.permitted_evidence_ids,
        expected_units=set(sel.selected_container_ids),
        config={},
        container_type=sel.container_type
    )
    bad_plan = ArtifactPlan(slides=[SlideModel(slide_type=SlideType.TITLE, title="Title", content=[])])
    v_res = val.validate(bad_plan, ctx)
    assert v_res.is_valid is False
    assert any(e.category == "COVERAGE" and "chapter" in e.message.lower() for e in v_res.errors)


def test_document_id_resolution_and_ambiguity_handling():
    """
    Assert:
    - Evidence references resolve Document.id unambiguously.
    - Multiple Document rows sharing upload_id without evidence raises ambiguity error.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    doc_a = Document(id="doc_A", upload_id="upl_shared", status="processed", review_state="APPROVED", extraction_timestamp="now", processing_time=1.0)
    doc_b = Document(id="doc_B", upload_id="upl_shared", status="processed", review_state="APPROVED", extraction_timestamp="now", processing_time=1.0)
    db.add_all([doc_a, doc_b])
    db.flush()

    # Version with no evidence and multiple documents sharing upload_id -> AMBIGUOUS
    snap = AcademicGraphSnapshot(
        id="snap_amb", upload_id="upl_shared", pipeline_run_id="p1", approval_version=1,
        approved_revision=1, base_graph_fingerprint="b", resolved_graph_fingerprint="r",
        approval_timestamp=time.time(), reviewer_id="rev",
        nodes=[{"node_id": "u1", "category": "UNIT", "title": "Unit 1", "anchor_key": "u1"}],
        edges=[]
    )
    db.add(snap)
    db.commit()

    kv = KnowledgeBuilder(db).compile_snapshot(snap.id)

    with pytest.raises(ValueError) as exc_amb:
        resolve_document_id_for_version(db, kv)
    assert "Ambiguous document association" in str(exc_amb.value)


# ---------------------------------------------------------------------------
# Closeout Tests: Fallback Removal, Ownership Verification, Contract Validation
# ---------------------------------------------------------------------------

def test_document_id_fallback_removed_and_ownership_enforced():
    """
    Assert:
    - Missing Document row in DB raises an explicit domain error (no fallback).
    - Evidence referencing non-existent Document raises an explicit error.
    - Evidence referencing Document with mismatched upload_id is rejected.
    - Client-supplied document_id in config is overridden by server-resolved Document.id.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Case 1: KnowledgeVersion with NO Document row in DB
    kv_no_doc = KnowledgeVersion(
        id="kv_no_doc",
        upload_id="upl_no_doc",
        snapshot_id="snap_no_doc",
        status="FINALIZED"
    )
    db.add(kv_no_doc)
    db.commit()

    # Must raise explicit ValueError, NOT fall back to upl_no_doc!
    with pytest.raises(ValueError) as exc_no_doc:
        resolve_document_id_for_version(db, kv_no_doc)
    assert "No Document found for upload_id 'upl_no_doc'" in str(exc_no_doc.value)

    # Case 2: Evidence points to non-existent document
    kv_bad_ev = KnowledgeVersion(id="kv_bad_ev", upload_id="upl_bad_ev", snapshot_id="s2", status="BUILDING")
    ent = KnowledgeEntity(id="ent_ghost", knowledge_version_id="kv_bad_ev", entity_type="CONCEPT", title="Ghost", content="...", stable_id="s_ghost")
    ev_ghost = KnowledgeEvidence(
        id="ev_ghost_id", entity_id="ent_ghost", source_node_id="u1", document_id="doc_does_not_exist",
        page_number=1, x0=10.0, y0=10.0, x1=50.0, y1=50.0, text_reference="ghost ref", section_title="S", provenance="comp"
    )
    db.add_all([kv_bad_ev, ent, ev_ghost])
    db.commit()
    kv_bad_ev.status = "FINALIZED"
    db.commit()

    with pytest.raises(ValueError) as exc_ghost:
        resolve_document_id_for_version(db, kv_bad_ev)
    assert "does not exist in the database" in str(exc_ghost.value)

    # Case 3: Evidence points to document whose upload_id mismatches version
    doc_other = Document(id="doc_other_id", upload_id="upl_foreign", status="processed", review_state="APPROVED", extraction_timestamp="now", processing_time=1.0)
    db.add(doc_other)
    kv_mismatch = KnowledgeVersion(id="kv_mismatch", upload_id="upl_local", snapshot_id="s3", status="BUILDING")
    ent_m = KnowledgeEntity(id="ent_m", knowledge_version_id="kv_mismatch", entity_type="CONCEPT", title="M", content="...", stable_id="s_m")
    ev_m = KnowledgeEvidence(
        id="ev_m_id", entity_id="ent_m", source_node_id="u1", document_id="doc_other_id",
        page_number=1, x0=10.0, y0=10.0, x1=50.0, y1=50.0, text_reference="m ref", section_title="S", provenance="comp"
    )
    db.add_all([kv_mismatch, ent_m, ev_m])
    db.commit()
    kv_mismatch.status = "FINALIZED"
    db.commit()

    with pytest.raises(ValueError) as exc_mismatch:
        resolve_document_id_for_version(db, kv_mismatch)
    assert "does not match version upload" in str(exc_mismatch.value)

    # Case 4: Client-supplied document_id in config is overridden by server-resolved Document.id
    doc_auth = Document(id="doc_auth_id", upload_id="upl_auth", status="processed", review_state="APPROVED", extraction_timestamp="now", processing_time=1.0)
    db.add(doc_auth)
    kv_auth = KnowledgeVersion(id="kv_auth", upload_id="upl_auth", snapshot_id="s4", status="BUILDING")
    ent_a = KnowledgeEntity(id="ent_a", knowledge_version_id="kv_auth", entity_type="UNIT", title="Unit Auth", content="...", stable_id="s_a")
    ev_a = KnowledgeEvidence(
        id="ev_a_id", entity_id="ent_a", source_node_id="u1", document_id="doc_auth_id",
        page_number=1, x0=10.0, y0=10.0, x1=50.0, y1=50.0, text_reference="a ref", section_title="S", provenance="comp"
    )
    db.add_all([kv_auth, ent_a, ev_a])
    db.commit()
    kv_auth.status = "FINALIZED"
    db.commit()

    effective_sel = resolve_effective_selection(
        db=db,
        version_id=kv_auth.id,
        upload_id="upl_auth",
        config={"document_id": "malicious_spoofed_doc_id"}
    )
    assert effective_sel.document_id == "doc_auth_id"
    assert effective_sel.document_id != "malicious_spoofed_doc_id"


def test_input_contract_rejected_malformed_selections(four_unit_db):
    """
    Assert that malformed selections are rejected at API/schema boundary:
    - String instead of list.
    - Null or invalid elements.
    - Unknown and foreign-version IDs.
    - Empty explicit selection.
    - Both selected_unit_ids and num_units.
    - Boolean, fractional, zero, or negative num_units.
    - Unrelated settings are preserved.
    """
    db = four_unit_db["db"]
    doc = four_unit_db["doc"]
    kv = four_unit_db["version"]
    u_map = four_unit_db["unit_map"]
    u1 = u_map["Unit 1"]
    service = ArtifactService(db)

    # 1. String instead of a list
    with pytest.raises(ValidationError) as exc1:
        ArtifactJobCreate(
            upload_id=doc.upload_id,
            knowledge_version_id=kv.id,
            config={"selected_unit_ids": "unit_1_string"}
        )
    assert "must be a list" in str(exc1.value)

    # 2. Null element in list
    with pytest.raises(ValidationError) as exc2:
        ArtifactJobCreate(
            upload_id=doc.upload_id,
            knowledge_version_id=kv.id,
            config={"selected_unit_ids": [u1.id, None]}
        )
    assert "cannot be null" in str(exc2.value)

    # 3. Invalid non-string element in list
    with pytest.raises(ValidationError) as exc3:
        ArtifactJobCreate(
            upload_id=doc.upload_id,
            knowledge_version_id=kv.id,
            config={"selected_unit_ids": [12345]}
        )
    assert "must be a string" in str(exc3.value)

    # 4. Empty string element in list
    with pytest.raises(ValidationError) as exc3b:
        ArtifactJobCreate(
            upload_id=doc.upload_id,
            knowledge_version_id=kv.id,
            config={"selected_unit_ids": ["   "]}
        )
    assert "cannot be an empty string" in str(exc3b.value)

    # 5. Empty explicit selection list
    with pytest.raises(ValidationError) as exc4:
        ArtifactJobCreate(
            upload_id=doc.upload_id,
            knowledge_version_id=kv.id,
            config={"selected_unit_ids": []}
        )
    assert "cannot be empty" in str(exc4.value)

    # 6. Both selected_unit_ids and num_units
    with pytest.raises(ValidationError) as exc5:
        ArtifactJobCreate(
            upload_id=doc.upload_id,
            knowledge_version_id=kv.id,
            config={"selected_unit_ids": [u1.id], "num_units": 1}
        )
    assert "Cannot specify both" in str(exc5.value)

    # 7. Boolean num_units (True or False)
    with pytest.raises(ValidationError) as exc6:
        ArtifactJobCreate(
            upload_id=doc.upload_id,
            knowledge_version_id=kv.id,
            config={"num_units": True}
        )
    assert "cannot be a boolean" in str(exc6.value)

    # 8. Fractional num_units (float)
    with pytest.raises(ValidationError) as exc7:
        ArtifactJobCreate(
            upload_id=doc.upload_id,
            knowledge_version_id=kv.id,
            config={"num_units": 2.5}
        )
    assert "must be an integer" in str(exc7.value)

    # 9. Zero num_units
    with pytest.raises(ValidationError) as exc8:
        ArtifactJobCreate(
            upload_id=doc.upload_id,
            knowledge_version_id=kv.id,
            config={"num_units": 0}
        )
    assert "greater than zero" in str(exc8.value)

    # 10. Negative num_units
    with pytest.raises(ValidationError) as exc9:
        ArtifactJobCreate(
            upload_id=doc.upload_id,
            knowledge_version_id=kv.id,
            config={"num_units": -3}
        )
    assert "greater than zero" in str(exc9.value)

    # 11. Unknown container ID (domain validation)
    with pytest.raises(HTTPException) as exc10:
        service.create_artifact_job(ArtifactJobCreate(
            upload_id=doc.upload_id,
            knowledge_version_id=kv.id,
            config={"selected_unit_ids": ["totally_unknown_uuid"]}
        ))
    assert exc10.value.status_code == 400
    assert "not found" in exc10.value.detail

    # 12. Non-container entity ID (topic/concept)
    topic_entity = four_unit_db["all_entities"]["Topic 1.1: Boolean Algebra"]
    t_id = topic_entity.id
    with pytest.raises(HTTPException) as exc11:
        service.create_artifact_job(ArtifactJobCreate(
            upload_id=doc.upload_id,
            knowledge_version_id=kv.id,
            config={"selected_unit_ids": [t_id]}
        ))
    assert exc11.value.status_code == 400
    assert "cannot be selected as a top-level unit container" in exc11.value.detail

    # 13. Unrelated settings are preserved without breaking
    job_ok = service.create_artifact_job(ArtifactJobCreate(
        upload_id=doc.upload_id,
        knowledge_version_id=kv.id,
        config={
            "selected_unit_ids": [u1.id],
            "audience_level": "advanced",
            "custom_theme": "dark_modern",
            "depth": "deep"
        }
    ))
    assert job_ok.config["selected_unit_ids"] == [u1.id]
    assert job_ok.config["audience_level"] == "advanced"
    assert job_ok.config["custom_theme"] == "dark_modern"
    assert job_ok.config["depth"] == "deep"
    assert job_ok.config["document_id"] == doc.id


# ---------------------------------------------------------------------------
# Arbitrary Selection: Parameterized Coverage on Dynamic Container IDs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("subset_indices", [
    [0],               # Unit 1 individually
    [1],               # Unit 2 individually
    [2],               # Unit 3 individually
    [3],               # Unit 4 individually
    [0, 2],            # Non-adjacent subset: Units 1 & 3
    [1, 3],            # Non-adjacent subset: Units 2 & 4
    [0, 1, 3],         # 3 units: Units 1, 2, 4
    [1, 2],            # Adjacent subset: Units 2 & 3
    [0, 3],            # First and last: Units 1 & 4
    [0, 1, 2, 3],      # All units
    [3, 1],            # Reverse input order: Units 4 & 2
    [3, 2, 1, 0],      # Reverse all units
])
def test_arbitrary_selection_parameterized(four_unit_db, subset_indices):
    """
    Assert:
    - Any single unit, multiple units, or all units can be selected.
    - Uses dynamically obtained container IDs (no hardcoded fixture numbers).
    - Preserves canonical source (textbook) order regardless of input order.
    - Permitted entities include selected containers and all their descendants.
    - Exclusively unselected containers and their exclusive descendants are strictly excluded.
    """
    db = four_unit_db["db"]
    doc = four_unit_db["doc"]
    kv = four_unit_db["version"]

    containers = get_selectable_containers(db, kv.id).containers
    container_ids = [c.id for c in containers]

    # Map requested indices to dynamic container IDs
    input_ids = [container_ids[i] for i in subset_indices]
    expected_canonical_ids = [container_ids[i] for i in sorted(subset_indices)]

    effective_sel = resolve_effective_selection(
        db=db,
        version_id=kv.id,
        upload_id=doc.upload_id,
        config={"selected_unit_ids": input_ids}
    )

    # 1. Canonical source order
    assert effective_sel.selected_container_ids == expected_canonical_ids

    # 2. Selected containers are included
    for cid in expected_canonical_ids:
        assert cid in effective_sel.permitted_entity_ids
        for did in effective_sel.container_to_descendants[cid]:
            assert did in effective_sel.permitted_entity_ids

    # 3. Exclusively unselected containers are excluded
    unselected_indices = set(range(len(container_ids))) - set(subset_indices)
    for u_idx in unselected_indices:
        u_id = container_ids[u_idx]
        assert u_id not in effective_sel.permitted_entity_ids


# ---------------------------------------------------------------------------
# Alternate Textbook Fixture: 5 Units
# ---------------------------------------------------------------------------

@pytest.fixture
def five_unit_db():
    """
    Textbook fixture with 5 Units to verify arbitrary selection is not hard-coded to 4 units.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    doc = Document(
        id="doc_five_units_textbook",
        upload_id="upl_five_units",
        status="processed",
        review_state="APPROVED",
        extraction_timestamp="2026-09-28T21:00:00",
        processing_time=1.5
    )
    db.add(doc)
    db.flush()

    for p in range(1, 6):
        db.add(DocumentPage(id=f"page_f_{p}", document_id=doc.id, page_number=p, width=612.0, height=792.0))

    unit_names = [
        "Foundations of Computing",
        "Data Structures",
        "Operating Systems",
        "Computer Networks",
        "Distributed Systems"
    ]
    nodes = []
    edges = []
    blocks = []

    for i, name in enumerate(unit_names, start=1):
        u_id = f"u_five_{i}"
        ch_id = f"ch_five_{i}"
        t_id = f"top_five_{i}"
        blk_id = f"blk_five_{i}"

        nodes.extend([
            {"node_id": u_id, "category": "UNIT", "title": f"Unit {i}: {name}", "anchor_key": f"u{i}", "target_block_id": blk_id},
            {"node_id": ch_id, "category": "CHAPTER", "title": f"Chapter {i}: Core Concepts", "anchor_key": f"ch{i}", "target_block_id": blk_id},
            {"node_id": t_id, "category": "TOPIC", "title": f"Topic {i}: Implementation", "anchor_key": f"t{i}", "target_block_id": blk_id}
        ])
        edges.extend([
            {"source_node_id": u_id, "target_node_id": ch_id, "edge_type": "CONTAINS"},
            {"source_node_id": ch_id, "target_node_id": t_id, "edge_type": "CONTAINS"}
        ])
        blocks.append(DocumentBlock(
            id=blk_id, document_id=doc.id, page_id=f"page_f_{i}", page_number=i, reading_order=0,
            block_type="PARAGRAPH", text=f"MARKER_FIVE_UNIT_{i}: Substantive text for {name}.",
            x0=50.0, y0=50.0, x1=500.0, y1=150.0
        ))

    db.add_all(blocks)
    db.flush()

    snap = AcademicGraphSnapshot(
        id="snap_five_units", upload_id=doc.upload_id, pipeline_run_id="p_five", approval_version=1,
        approved_revision=1, base_graph_fingerprint="bfp5", resolved_graph_fingerprint="rfp5",
        approval_timestamp=time.time(), reviewer_id="reviewer", nodes=nodes, edges=edges
    )
    db.add(snap)
    db.commit()

    kv = KnowledgeBuilder(db).compile_snapshot(snap.id)

    yield {"db": db, "doc": doc, "version": kv, "unit_names": unit_names}
    db.close()


def test_five_unit_textbook_arbitrary_selection(five_unit_db):
    """
    Assert arbitrary selection works identically on a 5-unit textbook:
    - Dynamically detects 5 units.
    - Selecting 1 unit.
    - Selecting 3 units in reverse order.
    - Selecting all 5 units.
    - num_units=3 selects top 3 in canonical order.
    """
    db = five_unit_db["db"]
    doc = five_unit_db["doc"]
    kv = five_unit_db["version"]

    containers = get_selectable_containers(db, kv.id).containers
    assert len(containers) == 5
    c_ids = [c.id for c in containers]

    # 1. Single unit selection (Unit 3)
    sel_single = resolve_effective_selection(db, kv.id, doc.upload_id, {"selected_unit_ids": [c_ids[2]]})
    assert sel_single.selected_container_ids == [c_ids[2]]
    assert c_ids[0] not in sel_single.permitted_entity_ids
    assert c_ids[4] not in sel_single.permitted_entity_ids

    # 2. Reverse order 3-unit selection: [Unit 5, Unit 3, Unit 1] -> resolved as [Unit 1, Unit 3, Unit 5]
    sel_rev = resolve_effective_selection(db, kv.id, doc.upload_id, {"selected_unit_ids": [c_ids[4], c_ids[2], c_ids[0]]})
    assert sel_rev.selected_container_ids == [c_ids[0], c_ids[2], c_ids[4]]
    assert c_ids[1] not in sel_rev.permitted_entity_ids
    assert c_ids[3] not in sel_rev.permitted_entity_ids

    # 3. All 5 units
    sel_all = resolve_effective_selection(db, kv.id, doc.upload_id, {"selected_unit_ids": c_ids})
    assert sel_all.selected_container_ids == c_ids

    # 4. num_units = 3 -> top 3 in canonical order
    sel_n3 = resolve_effective_selection(db, kv.id, doc.upload_id, {"num_units": 3})
    assert sel_n3.selected_container_ids == [c_ids[0], c_ids[1], c_ids[2]]


# ---------------------------------------------------------------------------
# Passage-Level Isolation Tests
# ---------------------------------------------------------------------------

def test_passage_isolation_selected_and_unselected_blocks_same_page(four_unit_db):
    """
    Assert:
    - Page 2 contains both selected and unselected blocks (blk_u1_p2 and blk_u2_p2).
    - Scope restricted to Unit 2 retrieves ONLY Unit 2's block.
    - Unit 1's neighboring block on the same page is strictly excluded.
    - Whole page text is NEVER admitted.
    """
    db = four_unit_db["db"]
    doc = four_unit_db["doc"]
    kv = four_unit_db["version"]
    u_map = four_unit_db["unit_map"]
    u2 = u_map["Unit 2"]

    effective_sel = resolve_effective_selection(db, kv.id, doc.upload_id, {"selected_unit_ids": [u2.id]})

    k_repo = KnowledgeRepository(db)
    d_repo = DocumentRepository(db)
    retriever = RetrievalService(k_repo, d_repo)

    result = retriever.retrieve(RetrievalRequest(
        query="register transfer processor design",
        scope=RetrievalScope(
            document_id=effective_sel.document_id,
            version_id=kv.id,
            allowed_entity_ids=list(effective_sel.permitted_entity_ids)
        ),
        options=RetrievalOptions(
            strategy="LEXICAL",
            include_evidence=True,
            include_passages=True
        )
    ))

    # Collect retrieved passages
    all_passage_texts = []
    for rent in result.entities:
        for p in rent.passages:
            all_passage_texts.append(p.text)

    all_text = " ".join(all_passage_texts)

    # Unit 2 block MUST be present
    assert "MARKER_UNIT_2_EXCLUSIVE" in all_text

    # Unit 1 block on the SAME PAGE MUST NOT be present
    assert "MARKER_UNIT_1_SAME_PAGE" not in all_text
    assert "MARKER_UNIT_1_EXCLUSIVE" not in all_text


def test_passage_isolation_overlapping_bounding_boxes():
    """
    Assert:
    - Two DocumentBlocks overlap on a page.
    - Evidence bounding box overlaps both blocks with larger intersection on Block 1.
    - PassageRetriever deterministically resolves to Block 1 without inventing splits or duplicating.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    doc = Document(id="doc_overlap", upload_id="upl_overlap", status="processed", review_state="APPROVED", extraction_timestamp="now", processing_time=1.0)
    page = DocumentPage(id="page_ov_1", document_id="doc_overlap", page_number=1, width=612.0, height=792.0)
    db.add_all([doc, page])
    db.flush()

    # Block 1: (100, 100) to (300, 300) -> Area 200x200 = 40,000
    blk1 = DocumentBlock(id="blk_ov_1", document_id=doc.id, page_id=page.id, page_number=1, reading_order=1,
                         block_type="PARAGRAPH", text="Block 1 Primary Content.", x0=100.0, y0=100.0, x1=300.0, y1=300.0)
    # Block 2: (250, 250) to (450, 450) -> Partially overlaps Block 1
    blk2 = DocumentBlock(id="blk_ov_2", document_id=doc.id, page_id=page.id, page_number=1, reading_order=2,
                         block_type="PARAGRAPH", text="Block 2 Overlapping Content.", x0=250.0, y0=250.0, x1=450.0, y1=450.0)
    db.add_all([blk1, blk2])
    db.flush()

    # Evidence: (150, 150) to (280, 280)
    # Overlap with Block 1: (150 to 280)x(150 to 280) = 130x130 = 16,900
    # Overlap with Block 2: (250 to 280)x(250 to 280) = 30x30 = 900
    ev = KnowledgeEvidence(
        id="ev_ov_1", entity_id="ent_1", source_node_id="n1", document_id=doc.id, page_number=1,
        x0=150.0, y0=150.0, x1=280.0, y1=280.0, text_reference="overlap reference", section_title="S", provenance="comp"
    )

    doc_repo = DocumentRepository(db)
    p_retriever = PassageRetriever(doc_repo)
    cand = EvidenceCandidate(evidence=ev, entity_id="ent_1", is_stale=False)

    passages = p_retriever.retrieve_passages([cand], ResolvedScope(document_id=doc.id, version_id="v1"))
    assert len(passages) == 1
    assert passages[0].block_id == "blk_ov_1"
    assert passages[0].text == "Block 1 Primary Content."


def test_passage_isolation_missing_bounding_boxes():
    """
    Assert:
    - When evidence lacks bounding box coordinates (None), PassageRetriever refuses to invent coordinates
      or admit the entire page text.
    - Emits a clear diagnostic ("MISSING_BOUNDING_BOX").
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    doc = Document(id="doc_missing_coords", upload_id="upl_missing_coords", status="processed", review_state="APPROVED", extraction_timestamp="now", processing_time=1.0)
    page = DocumentPage(id="page_mc_1", document_id=doc.id, page_number=1, width=612.0, height=792.0)
    blk = DocumentBlock(id="blk_mc_1", document_id=doc.id, page_id=page.id, page_number=1, reading_order=1,
                        block_type="PARAGRAPH", text="Page whole text that must NOT leak.", x0=100.0, y0=100.0, x1=400.0, y1=300.0)
    db.add_all([doc, page, blk])
    db.flush()

    ev_missing = KnowledgeEvidence(
        id="ev_mc_1", entity_id="ent_1", source_node_id="n1", document_id=doc.id, page_number=1,
        x0=None, y0=None, x1=None, y1=None, text_reference="reference with no coords", section_title="S", provenance="comp"
    )

    doc_repo = DocumentRepository(db)
    p_retriever = PassageRetriever(doc_repo)
    cand = EvidenceCandidate(evidence=ev_missing, entity_id="ent_1", is_stale=False)

    passages = p_retriever.retrieve_passages([cand], ResolvedScope(document_id=doc.id, version_id="v1"))

    # Must return empty list, NOT whole page text!
    assert len(passages) == 0

    # Must emit explicit diagnostic
    assert len(p_retriever.diagnostics) == 1
    assert "MISSING_BOUNDING_BOX" in p_retriever.diagnostics[0]
    assert "Whole-page fallback suppressed" in p_retriever.diagnostics[0]


def test_passage_isolation_mixed_source_block():
    """
    Assert:
    - A physical source block contains text referenced by both selected entity and unselected entity.
    - When selected entity is retrieved, the block is retrieved verbatim without inventing an artificial split.
    - Only permitted entity IDs are associated with the passage.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    doc = Document(id="doc_mixed", upload_id="upl_mixed", status="processed", review_state="APPROVED", extraction_timestamp="now", processing_time=1.0)
    page = DocumentPage(id="page_m_1", document_id=doc.id, page_number=1, width=612.0, height=792.0)
    blk = DocumentBlock(id="blk_mixed", document_id=doc.id, page_id=page.id, page_number=1, reading_order=1,
                        block_type="PARAGRAPH", text="Combined definition of Data and Signal.", x0=100.0, y0=100.0, x1=400.0, y1=300.0)
    db.add_all([doc, page, blk])
    db.flush()

    # Evidence for permitted entity
    ev_permitted = KnowledgeEvidence(
        id="ev_perm", entity_id="ent_data_selected", source_node_id="n_data", document_id=doc.id, page_number=1,
        x0=100.0, y0=100.0, x1=400.0, y1=300.0, text_reference="Combined definition", section_title="S", provenance="comp"
    )

    doc_repo = DocumentRepository(db)
    p_retriever = PassageRetriever(doc_repo)
    cand_perm = EvidenceCandidate(evidence=ev_permitted, entity_id="ent_data_selected", is_stale=False)

    passages = p_retriever.retrieve_passages([cand_perm], ResolvedScope(document_id=doc.id, version_id="v1"))
    assert len(passages) == 1
    assert passages[0].block_id == "blk_mixed"
    assert passages[0].text == "Combined definition of Data and Signal."
    assert passages[0].entity_ids == ["ent_data_selected"]


@pytest.mark.asyncio
async def test_reproduce_mixed_block_leak():
    """
    REPRODUCE THE LEAK:
    Create a regression fixture containing one physical block with:
    - A distinctive statement belonging to a selected container (Unit 2).
    - A distinctive statement belonging exclusively to an unselected container (Unit 1).
    - Evidence associations reflecting that ambiguity.
    Capture the actual context sent through the planner's provider boundary.
    Demonstrate that the unselected statement leaks into the planner's LLM prompt.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    doc_id = "doc_repro_leak"
    upload_id = "upl_repro_leak"
    doc = Document(
        id=doc_id, upload_id=upload_id, status="processed", review_state="APPROVED",
        extraction_timestamp="2026-09-28T21:00:00", processing_time=1.0
    )
    page = DocumentPage(id="page_repro_1", document_id=doc_id, page_number=1, width=612.0, height=792.0)
    
    # ONE physical block containing both selected and unselected statements
    mixed_text = (
        "MARKER_UNIT2_ALLOWED: Unit 2 covers advanced deep learning architectures and backpropagation. "
        "MARKER_UNIT1_EXCLUSIVE_LEAK: Unit 1 exclusively covers introductory setup and installation of Python packages."
    )
    blk = DocumentBlock(
        id="blk_mixed_leak", document_id=doc_id, page_id=page.id, page_number=1, reading_order=1,
        block_type="PARAGRAPH", text=mixed_text,
        x0=100.0, y0=100.0, x1=500.0, y1=300.0
    )
    db.add_all([doc, page, blk])

    # Snapshot and KnowledgeVersion
    snapshot = AcademicGraphSnapshot(
        id="snap_repro", upload_id=upload_id, pipeline_run_id="run_repro", approval_version=1,
        approved_revision=1, base_graph_fingerprint="fp1",
        resolved_graph_fingerprint="fp2",
        reviewer_id="admin", approval_timestamp=time.time(),
        nodes=[], edges=[]
    )
    k_version = KnowledgeVersion(
        id="kv_repro", upload_id=upload_id, snapshot_id=snapshot.id, status="FINALIZED"
    )
    db.add_all([snapshot, k_version])

    # Unit 1 (Unselected)
    u1 = KnowledgeEntity(
        id="unit_1_repro", knowledge_version_id=k_version.id, title="Unit 1: Introduction",
        entity_type="UNIT", content="Introduction to Python", stable_id="u1_stable"
    )
    # Unit 2 (Selected)
    u2 = KnowledgeEntity(
        id="unit_2_repro", knowledge_version_id=k_version.id, title="Unit 2: Deep Learning",
        entity_type="UNIT", content="Deep Learning Architectures", stable_id="u2_stable"
    )
    db.add_all([u1, u2])

    # Evidence for Unit 2 intersecting blk_mixed_leak
    ev2 = KnowledgeEvidence(
        id="ev_u2_repro", entity_id=u2.id, source_node_id=u2.id, document_id=doc_id, page_number=1,
        x0=100.0, y0=100.0, x1=500.0, y1=200.0,
        text_reference="Unit 2 covers advanced deep learning architectures and backpropagation.",
        section_title="Deep Learning", provenance="EXPLICIT_CLASSIFIER"
    )
    # Evidence for Unit 1 intersecting blk_mixed_leak
    ev1 = KnowledgeEvidence(
        id="ev_u1_repro", entity_id=u1.id, source_node_id=u1.id, document_id=doc_id, page_number=1,
        x0=100.0, y0=200.0, x1=500.0, y1=300.0,
        text_reference="Unit 1 exclusively covers introductory setup and installation of Python packages.",
        section_title="Introduction", provenance="EXPLICIT_CLASSIFIER"
    )
    db.add_all([ev1, ev2])
    db.commit()

    # Create job selecting ONLY Unit 2
    job_read = ArtifactJobRead(
        id="job_repro_leak",
        upload_id=upload_id,
        knowledge_version_id=k_version.id,
        artifact_type=ArtifactType.PPTX,
        status="PLANNING",
        config={"selected_unit_ids": [u2.id], "include_examples": False, "include_questions": False},
        created_at=time.time(),
        updated_at=time.time()
    )

    k_repo = KnowledgeRepository(db)
    d_repo = DocumentRepository(db)
    retrieval_service = RetrievalService(k_repo, d_repo, RankingWeights())
    provider = CapturingLLMProvider()
    planner = ArtifactPlanner(k_repo, retrieval_service, provider)

    await planner.plan(job_read)

    assert len(provider.captured_requests) > 0
    captured_prompt = provider.captured_requests[0].prompt

    # VERIFY THE REPAIRED ISOLATION:
    # 1. Distinctive statement for selected container (Unit 2) IS present in the captured prompt
    assert "Unit 2 covers advanced deep learning architectures and backpropagation." in captured_prompt
    # 2. Distinctive statement belonging exclusively to unselected container (Unit 1) is EXCLUDED from captured prompt
    assert "MARKER_UNIT1_EXCLUSIVE_LEAK" not in captured_prompt
    assert "introductory setup and installation of Python packages" not in captured_prompt
    # 3. Diagnostic is recorded
    assert any("MIXED_BLOCK_ISOLATED" in d for d in retrieval_service.passage_retriever.diagnostics)


def test_passage_isolation_mixed_block_without_verified_span_excluded():
    """
    Assert:
    - When a physical block contains mixed content (both selected and unselected),
      and evidence for the selected entity lacks a verified source span (e.g. text_reference is None),
      the ambiguous block is excluded rather than guessed or admitted verbatim.
    - Emits structured diagnostic 'MIXED_BLOCK_EXCLUDED'.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    doc = Document(id="doc_m_ex", upload_id="upl_m_ex", status="processed", review_state="APPROVED", extraction_timestamp="now", processing_time=1.0)
    page = DocumentPage(id="page_m_ex", document_id=doc.id, page_number=1, width=612.0, height=792.0)
    blk = DocumentBlock(
        id="blk_m_ex", document_id=doc.id, page_id=page.id, page_number=1, reading_order=1,
        block_type="PARAGRAPH", text="Mixed block: Selected Unit 2 statement. Unselected Unit 1 statement.",
        x0=100.0, y0=100.0, x1=500.0, y1=300.0
    )
    db.add_all([doc, page, blk])

    # Unselected evidence on this block
    ev_unselected = KnowledgeEvidence(
        id="ev_unsel", entity_id="ent_unit1", source_node_id="n1", document_id=doc.id, page_number=1,
        x0=100.0, y0=200.0, x1=500.0, y1=300.0,
        text_reference="Unselected Unit 1 statement.", section_title="S", provenance="EXPLICIT_CLASSIFIER"
    )
    # Selected evidence on this block WITHOUT a verified span (text_reference=None)
    ev_selected = KnowledgeEvidence(
        id="ev_sel", entity_id="ent_unit2", source_node_id="n2", document_id=doc.id, page_number=1,
        x0=100.0, y0=100.0, x1=500.0, y1=200.0,
        text_reference=None, section_title="S", provenance="EXPLICIT_CLASSIFIER"
    )
    db.add_all([ev_unselected, ev_selected])
    db.flush()

    doc_repo = DocumentRepository(db)
    k_repo = KnowledgeRepository(db)
    p_retriever = PassageRetriever(doc_repo, knowledge_repo=k_repo)
    cand = EvidenceCandidate(evidence=ev_selected, entity_id="ent_unit2", is_stale=False)

    passages = p_retriever.retrieve_passages(
        [cand],
        ResolvedScope(document_id=doc.id, version_id="v1", allowed_entity_ids=["ent_unit2"])
    )

    # Must be excluded!
    assert len(passages) == 0
    assert any("MIXED_BLOCK_EXCLUDED" in d for d in p_retriever.diagnostics)
    assert ev_selected.id in p_retriever.excluded_evidence_ids


def test_passage_isolation_overlapping_cross_scope_candidates_disambiguated():
    """
    Assert:
    - Coordinate-based lookup: Geometric overlap is candidate matching only, not proof of semantic ownership.
    - When candidates from different scopes overlap, do NOT resolve solely by largest intersection area.
    - Validated provenance (matching text_reference) disambiguates and picks the correct block.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    doc = Document(id="doc_ov_prov", upload_id="upl_ov_prov", status="processed", review_state="APPROVED", extraction_timestamp="now", processing_time=1.0)
    page = DocumentPage(id="page_ov_prov", document_id=doc.id, page_number=1, width=612.0, height=792.0)

    # Block A: Belongs to unselected scope, has LARGER geometric overlap (120 x 100 = 12,000)
    blk_a = DocumentBlock(
        id="blk_a_unselected", document_id=doc.id, page_id=page.id, page_number=1, reading_order=1,
        block_type="PARAGRAPH", text="Block A: Introductory Unselected Scope Material.",
        x0=100.0, y0=100.0, x1=220.0, y1=200.0
    )
    # Block B: Belongs to selected scope, has SMALLER geometric overlap (40 x 100 = 4,000)
    blk_b = DocumentBlock(
        id="blk_b_selected", document_id=doc.id, page_id=page.id, page_number=1, reading_order=2,
        block_type="PARAGRAPH", text="Block B: Specific Machine Learning Gradient Descent Method.",
        x0=220.0, y0=100.0, x1=300.0, y1=200.0
    )
    db.add_all([doc, page, blk_a, blk_b])

    # Unselected evidence on Block A
    ev_unsel = KnowledgeEvidence(
        id="ev_unsel_a", entity_id="ent_unselected", source_node_id="nu", document_id=doc.id, page_number=1,
        x0=100.0, y0=100.0, x1=220.0, y1=200.0,
        text_reference="Block A: Introductory Unselected Scope Material.", section_title="S", provenance="EXPLICIT_CLASSIFIER"
    )
    # Selected evidence with bounding box spanning across both blocks (100 to 260)
    # Overlap with Block A: (100 to 220) = 120 x 100 = 12,000
    # Overlap with Block B: (220 to 260) = 40 x 100 = 4,000
    # Provenance matches Block B!
    ev_sel = KnowledgeEvidence(
        id="ev_sel_b", entity_id="ent_selected", source_node_id="ns", document_id=doc.id, page_number=1,
        x0=100.0, y0=100.0, x1=260.0, y1=200.0,
        text_reference="Block B: Specific Machine Learning Gradient Descent Method.", section_title="S", provenance="EXPLICIT_CLASSIFIER"
    )
    db.add_all([ev_unsel, ev_sel])
    db.flush()

    doc_repo = DocumentRepository(db)
    k_repo = KnowledgeRepository(db)
    p_retriever = PassageRetriever(doc_repo, knowledge_repo=k_repo)
    cand = EvidenceCandidate(evidence=ev_sel, entity_id="ent_selected", is_stale=False)

    passages = p_retriever.retrieve_passages(
        [cand],
        ResolvedScope(document_id=doc.id, version_id="v1", allowed_entity_ids=["ent_selected"])
    )

    # Validated provenance selects Block B despite smaller geometric area!
    assert len(passages) == 1
    assert passages[0].block_id == "blk_b_selected"
    assert "Block B: Specific Machine Learning Gradient Descent Method." in passages[0].text
    assert "Block A" not in passages[0].text


def test_passage_isolation_overlapping_cross_scope_candidates_ambiguous_excluded():
    """
    Assert:
    - When evidence overlaps multiple candidate blocks from different scopes,
      and validated provenance does NOT disambiguate,
      exclude the ambiguous passage and record a structured diagnostic 'CROSS_SCOPE_AMBIGUITY'.
    - Do NOT pick solely by largest intersection area.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    doc = Document(id="doc_ov_amb", upload_id="upl_ov_amb", status="processed", review_state="APPROVED", extraction_timestamp="now", processing_time=1.0)
    page = DocumentPage(id="page_ov_amb", document_id=doc.id, page_number=1, width=612.0, height=792.0)

    blk_a = DocumentBlock(
        id="blk_a_amb", document_id=doc.id, page_id=page.id, page_number=1, reading_order=1,
        block_type="PARAGRAPH", text="Block A: Content", x0=100.0, y0=100.0, x1=250.0, y1=200.0
    )
    blk_b = DocumentBlock(
        id="blk_b_amb", document_id=doc.id, page_id=page.id, page_number=1, reading_order=2,
        block_type="PARAGRAPH", text="Block B: Content", x0=250.0, y0=100.0, x1=400.0, y1=200.0
    )
    db.add_all([doc, page, blk_a, blk_b])

    # Unselected evidence on Block A
    ev_unsel = KnowledgeEvidence(
        id="ev_u_amb", entity_id="ent_unselected", source_node_id="nu", document_id=doc.id, page_number=1,
        x0=100.0, y0=100.0, x1=250.0, y1=200.0, text_reference="Block A: Content", section_title="S", provenance="EXPLICIT_CLASSIFIER"
    )
    # Selected evidence overlaps both, but text_reference is None (no validated provenance)
    ev_sel = KnowledgeEvidence(
        id="ev_s_amb", entity_id="ent_selected", source_node_id="ns", document_id=doc.id, page_number=1,
        x0=100.0, y0=100.0, x1=350.0, y1=200.0, text_reference=None, section_title="S", provenance="EXPLICIT_CLASSIFIER"
    )
    db.add_all([ev_unsel, ev_sel])
    db.flush()

    doc_repo = DocumentRepository(db)
    k_repo = KnowledgeRepository(db)
    p_retriever = PassageRetriever(doc_repo, knowledge_repo=k_repo)
    cand = EvidenceCandidate(evidence=ev_sel, entity_id="ent_selected", is_stale=False)

    passages = p_retriever.retrieve_passages(
        [cand],
        ResolvedScope(document_id=doc.id, version_id="v1", allowed_entity_ids=["ent_selected"])
    )

    # Must be excluded!
    assert len(passages) == 0
    assert any("CROSS_SCOPE_AMBIGUITY" in d for d in p_retriever.diagnostics)
    assert ev_sel.id in p_retriever.excluded_evidence_ids


def test_passage_isolation_missing_coordinates_with_valid_exact_source_reference():
    """
    Assert:
    - A missing bounding box does not require rejection if another trustworthy
      source reference establishes the exact allowed text.
    - Resolves exact span with structured diagnostic 'EXACT_SPAN_RESOLVED'.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    doc = Document(id="doc_mc_exact", upload_id="upl_mc_exact", status="processed", review_state="APPROVED", extraction_timestamp="now", processing_time=1.0)
    page = DocumentPage(id="page_mc_exact", document_id=doc.id, page_number=1, width=612.0, height=792.0)
    blk = DocumentBlock(
        id="blk_mc_exact", document_id=doc.id, page_id=page.id, page_number=1, reading_order=1,
        block_type="PARAGRAPH", text="Section intro. In computer architecture, pipelining overlaps instruction execution. Summary.",
        x0=100.0, y0=100.0, x1=500.0, y1=300.0
    )
    db.add_all([doc, page, blk])

    ev = KnowledgeEvidence(
        id="ev_mc_valid", entity_id="ent_pipe", source_node_id="n_pipe", document_id=doc.id, page_number=1,
        x0=None, y0=None, x1=None, y1=None,
        text_reference="In computer architecture, pipelining overlaps instruction execution.",
        section_title="Pipelining", provenance="EXPLICIT_CLASSIFIER"
    )
    db.add(ev)
    db.flush()

    doc_repo = DocumentRepository(db)
    k_repo = KnowledgeRepository(db)
    p_retriever = PassageRetriever(doc_repo, knowledge_repo=k_repo)
    cand = EvidenceCandidate(evidence=ev, entity_id="ent_pipe", is_stale=False)

    passages = p_retriever.retrieve_passages(
        [cand],
        ResolvedScope(document_id=doc.id, version_id="v1", allowed_entity_ids=["ent_pipe"])
    )

    assert len(passages) == 1
    assert passages[0].text == "In computer architecture, pipelining overlaps instruction execution."
    assert any("EXACT_SPAN_RESOLVED" in d for d in p_retriever.diagnostics)


def test_passage_isolation_missing_coordinates_without_trustworthy_reference():
    """
    Assert:
    - Missing coordinates without a trustworthy source reference in the document
      is excluded with diagnostic 'MISSING_BOUNDING_BOX'.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    doc = Document(id="doc_mc_fail", upload_id="upl_mc_fail", status="processed", review_state="APPROVED", extraction_timestamp="now", processing_time=1.0)
    page = DocumentPage(id="page_mc_fail", document_id=doc.id, page_number=1, width=612.0, height=792.0)
    blk = DocumentBlock(
        id="blk_mc_fail", document_id=doc.id, page_id=page.id, page_number=1, reading_order=1,
        block_type="PARAGRAPH", text="Completely unrelated document text.",
        x0=100.0, y0=100.0, x1=500.0, y1=300.0
    )
    db.add_all([doc, page, blk])

    ev = KnowledgeEvidence(
        id="ev_mc_unmatched", entity_id="ent_unmatched", source_node_id="nu", document_id=doc.id, page_number=1,
        x0=None, y0=None, x1=None, y1=None,
        text_reference="Phantom text not present in document blocks.",
        section_title="Phantom", provenance="EXPLICIT_CLASSIFIER"
    )
    db.add(ev)
    db.flush()

    doc_repo = DocumentRepository(db)
    k_repo = KnowledgeRepository(db)
    p_retriever = PassageRetriever(doc_repo, knowledge_repo=k_repo)
    cand = EvidenceCandidate(evidence=ev, entity_id="ent_unmatched", is_stale=False)

    passages = p_retriever.retrieve_passages(
        [cand],
        ResolvedScope(document_id=doc.id, version_id="v1", allowed_entity_ids=["ent_unmatched"])
    )

    assert len(passages) == 0
    assert any("MISSING_BOUNDING_BOX" in d for d in p_retriever.diagnostics)
    assert ev.id in p_retriever.excluded_evidence_ids


def test_passage_isolation_legitimate_shared_descendants(four_unit_db):
    """
    Assert:
    - Legitimate shared content reachable from selected containers remains permitted.
    - Concept shared across Unit 2 and Unit 3 is NOT confused with exclusively unselected text.
    """
    db = four_unit_db["db"]
    doc = four_unit_db["doc"]
    k_version = four_unit_db["version"]
    u2 = four_unit_db["unit_map"]["Unit 2"]

    # When Unit 2 is selected:
    effective_selection = resolve_effective_selection(
        db=db,
        upload_id=k_version.upload_id,
        version_id=k_version.id,
        config={"selected_unit_ids": [u2.id]}
    )

    # Shared concept must be in permitted entities
    shared_concept = db.query(KnowledgeEntity).filter(
        KnowledgeEntity.knowledge_version_id == k_version.id,
        KnowledgeEntity.title == "Shared Pipeline Concept"
    ).first()
    assert shared_concept is not None
    assert shared_concept.id in effective_selection.permitted_entity_ids

    # Retrieval must permit shared concept evidence and passages
    doc_repo = DocumentRepository(db)
    k_repo = KnowledgeRepository(db)
    retrieval_service = RetrievalService(k_repo, doc_repo, RankingWeights())

    res = retrieval_service.retrieve(
        RetrievalRequest(
            query="Shared Pipeline Concept",
            scope=RetrievalScope(
                document_id=doc.id,
                version_id=k_version.id,
                allowed_entity_ids=list(effective_selection.permitted_entity_ids)
            ),
            options=RetrievalOptions(strategy="LEXICAL", include_passages=True, include_evidence=True)
        )
    )

    # Shared concept passages are permitted!
    shared_retrieved = [re for re in res.entities if re.entity.id == shared_concept.id]
    assert len(shared_retrieved) == 1
    assert len(shared_retrieved[0].passages) >= 1
    assert "MARKER_SHARED_CONCEPT" in shared_retrieved[0].passages[0].text


@pytest.mark.asyncio
async def test_selected_container_left_without_usable_evidence_halts_before_provider():
    """
    Assert:
    - If exclusion leaves a selected container without usable substantive evidence,
      stop before provider invocation with an actionable message identifying
      the affected container and source page/block.
    - Do NOT call provider or produce a headings-only deck.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    doc_id = "doc_halt_test"
    upload_id = "upl_halt_test"
    doc = Document(id=doc_id, upload_id=upload_id, status="processed", review_state="APPROVED", extraction_timestamp="now", processing_time=1.0)
    page = DocumentPage(id="page_h_1", document_id=doc_id, page_number=1, width=612.0, height=792.0)
    # Mixed block with unselected content
    blk = DocumentBlock(
        id="blk_h_mixed", document_id=doc_id, page_id=page.id, page_number=1, reading_order=1,
        block_type="PARAGRAPH", text="Mixed Block: Selected U2 content. Unselected U1 content.",
        x0=100.0, y0=100.0, x1=500.0, y1=300.0
    )
    db.add_all([doc, page, blk])

    snapshot = AcademicGraphSnapshot(
        id="snap_h", upload_id=upload_id, pipeline_run_id="run_h", approval_version=1,
        approved_revision=1, base_graph_fingerprint="fp1", resolved_graph_fingerprint="fp2",
        reviewer_id="admin", approval_timestamp=time.time(), nodes=[], edges=[]
    )
    k_version = KnowledgeVersion(id="kv_h", upload_id=upload_id, snapshot_id=snapshot.id, status="FINALIZED")
    db.add_all([snapshot, k_version])

    u1 = KnowledgeEntity(id="u1_h", knowledge_version_id=k_version.id, title="Unit 1: Excluded", entity_type="UNIT", content="U1", stable_id="u1_s")
    u2 = KnowledgeEntity(id="u2_h", knowledge_version_id=k_version.id, title="Unit 2: Target", entity_type="UNIT", content="U2", stable_id="u2_s")
    db.add_all([u1, u2])

    ev_unselected = KnowledgeEvidence(
        id="ev_u1_h", entity_id=u1.id, source_node_id=u1.id, document_id=doc_id, page_number=1,
        x0=100.0, y0=200.0, x1=500.0, y1=300.0, text_reference="Unselected U1 content.", section_title="S", provenance="EXPLICIT_CLASSIFIER"
    )
    # Target container evidence lacks verified span on this mixed block (text_reference=None)
    # so it gets excluded, leaving Unit 2 with NO usable substantive evidence!
    ev_selected = KnowledgeEvidence(
        id="ev_u2_h", entity_id=u2.id, source_node_id=u2.id, document_id=doc_id, page_number=1,
        x0=100.0, y0=100.0, x1=500.0, y1=200.0, text_reference=None, section_title="S", provenance="EXPLICIT_CLASSIFIER"
    )
    db.add_all([ev_unselected, ev_selected])
    db.commit()

    job_read = ArtifactJobRead(
        id="job_h_test", upload_id=upload_id, knowledge_version_id=k_version.id, artifact_type=ArtifactType.PPTX,
        status="PLANNING", config={"selected_unit_ids": [u2.id], "include_examples": False, "include_questions": False},
        created_at=time.time(), updated_at=time.time()
    )

    k_repo = KnowledgeRepository(db)
    d_repo = DocumentRepository(db)
    retrieval_service = RetrievalService(k_repo, d_repo, RankingWeights())
    provider = CapturingLLMProvider()
    planner = ArtifactPlanner(k_repo, retrieval_service, provider)

    # Must raise GroundingValidationError with actionable message identifying Unit 2
    with pytest.raises(GroundingValidationError) as exc_info:
        await planner.plan(job_read)

    err_msg = str(exc_info.value)
    assert "Unit 2: Target" in err_msg
    assert "no usable substantive evidence" in err_msg
    # Provider must NEVER have been called!
    assert len(provider.captured_requests) == 0


@pytest.mark.asyncio
async def test_no_excluded_marker_reaches_any_provider_context_field():
    """
    Assert:
    - Trace all text entering the planning prompt:
      entity content, evidence text_reference, resolved passages, previous/next context.
    - Zero excluded markers reach any field of the LLM prompt.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    doc_id = "doc_all_fields"
    upload_id = "upl_all_fields"
    doc = Document(id=doc_id, upload_id=upload_id, status="processed", review_state="APPROVED", extraction_timestamp="now", processing_time=1.0)
    page = DocumentPage(id="page_af_1", document_id=doc_id, page_number=1, width=612.0, height=792.0)

    # Previous block with unselected marker
    blk_prev = DocumentBlock(
        id="blk_af_prev", document_id=doc_id, page_id=page.id, page_number=1, reading_order=1,
        block_type="PARAGRAPH", text="LEAK_MARKER_PREVIOUS_BLOCK: Unselected preamble.",
        x0=50.0, y0=50.0, x1=500.0, y1=100.0, next_block_id="blk_af_current"
    )
    # Current mixed block
    blk_curr = DocumentBlock(
        id="blk_af_current", document_id=doc_id, page_id=page.id, page_number=1, reading_order=2,
        block_type="PARAGRAPH",
        text="LEAK_MARKER_MIXED_UNSELECTED: Unselected topic. ALLOWED_MARKER_SELECTED: Core permitted unit content.",
        x0=50.0, y0=110.0, x1=500.0, y1=250.0,
        previous_block_id="blk_af_prev", next_block_id="blk_af_next"
    )
    # Next block with unselected marker
    blk_next = DocumentBlock(
        id="blk_af_next", document_id=doc_id, page_id=page.id, page_number=1, reading_order=3,
        block_type="PARAGRAPH", text="LEAK_MARKER_NEXT_BLOCK: Unselected postscript.",
        x0=50.0, y0=260.0, x1=500.0, y1=350.0, previous_block_id="blk_af_current"
    )
    db.add_all([doc, page, blk_prev, blk_curr, blk_next])

    snapshot = AcademicGraphSnapshot(
        id="snap_af", upload_id=upload_id, pipeline_run_id="run_af", approval_version=1,
        approved_revision=1, base_graph_fingerprint="fp1", resolved_graph_fingerprint="fp2",
        reviewer_id="admin", approval_timestamp=time.time(), nodes=[], edges=[]
    )
    k_version = KnowledgeVersion(id="kv_af", upload_id=upload_id, snapshot_id=snapshot.id, status="FINALIZED")
    db.add_all([snapshot, k_version])

    # Unselected entity with distinctive content
    u1 = KnowledgeEntity(
        id="u1_af", knowledge_version_id=k_version.id, title="Unit 1",
        entity_type="UNIT", content="LEAK_MARKER_ENTITY_U1_CONTENT", stable_id="u1_s"
    )
    # Selected entity
    u2 = KnowledgeEntity(
        id="u2_af", knowledge_version_id=k_version.id, title="Unit 2",
        entity_type="UNIT", content="Permitted Unit 2 content.", stable_id="u2_s"
    )
    db.add_all([u1, u2])

    # Unselected evidence
    ev_unsel = KnowledgeEvidence(
        id="ev_u1_af", entity_id=u1.id, source_node_id=u1.id, document_id=doc_id, page_number=1,
        x0=50.0, y0=110.0, x1=500.0, y1=180.0,
        text_reference="LEAK_MARKER_MIXED_UNSELECTED: Unselected topic.",
        section_title="S", provenance="EXPLICIT_CLASSIFIER"
    )
    # Selected evidence with verified span
    ev_sel = KnowledgeEvidence(
        id="ev_u2_af", entity_id=u2.id, source_node_id=u2.id, document_id=doc_id, page_number=1,
        x0=50.0, y0=180.0, x1=500.0, y1=250.0,
        text_reference="ALLOWED_MARKER_SELECTED: Core permitted unit content.",
        section_title="S", provenance="EXPLICIT_CLASSIFIER"
    )
    db.add_all([ev_unsel, ev_sel])
    db.commit()

    job_read = ArtifactJobRead(
        id="job_af_test", upload_id=upload_id, knowledge_version_id=k_version.id, artifact_type=ArtifactType.PPTX,
        status="PLANNING", config={"selected_unit_ids": [u2.id], "include_examples": False, "include_questions": False},
        created_at=time.time(), updated_at=time.time()
    )

    k_repo = KnowledgeRepository(db)
    d_repo = DocumentRepository(db)
    retrieval_service = RetrievalService(k_repo, d_repo, RankingWeights())
    provider = CapturingLLMProvider()
    planner = ArtifactPlanner(k_repo, retrieval_service, provider)

    await planner.plan(job_read)

    assert len(provider.captured_requests) > 0
    prompt = provider.captured_requests[0].prompt

    # NONE of the excluded markers must reach the provider prompt in any field!
    assert "LEAK_MARKER_PREVIOUS_BLOCK" not in prompt
    assert "LEAK_MARKER_MIXED_UNSELECTED" not in prompt
    assert "LEAK_MARKER_NEXT_BLOCK" not in prompt
    assert "LEAK_MARKER_ENTITY_U1_CONTENT" not in prompt

    # Permitted marker MUST be present
    assert "ALLOWED_MARKER_SELECTED: Core permitted unit content." in prompt


def test_unscoped_retrieval_remains_functional():
    """
    Assert:
    - Ordinary unscoped retrieval behavior is preserved where selection restrictions do not apply.
    - Admits full block text and does not apply mixed-block exclusions.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    doc = Document(id="doc_unscoped", upload_id="upl_unscoped", status="processed", review_state="APPROVED", extraction_timestamp="now", processing_time=1.0)
    page = DocumentPage(id="page_unscoped", document_id=doc.id, page_number=1, width=612.0, height=792.0)
    blk = DocumentBlock(
        id="blk_unscoped", document_id=doc.id, page_id=page.id, page_number=1, reading_order=1,
        block_type="PARAGRAPH", text="Full textbook paragraph on thermodynamics.",
        x0=100.0, y0=100.0, x1=500.0, y1=300.0
    )
    db.add_all([doc, page, blk])

    snapshot = AcademicGraphSnapshot(
        id="snap_u", upload_id=doc.upload_id, pipeline_run_id="run_u", approval_version=1,
        approved_revision=1, base_graph_fingerprint="fp1", resolved_graph_fingerprint="fp2",
        reviewer_id="admin", approval_timestamp=time.time(), nodes=[], edges=[]
    )
    k_version = KnowledgeVersion(id="kv_u", upload_id=doc.upload_id, snapshot_id=snapshot.id, status="FINALIZED")
    db.add_all([snapshot, k_version])

    ent = KnowledgeEntity(id="ent_u", knowledge_version_id=k_version.id, title="Thermodynamics", entity_type="CONCEPT", content="Heat", stable_id="th_s")
    ev = KnowledgeEvidence(
        id="ev_u", entity_id=ent.id, source_node_id=ent.id, document_id=doc.id, page_number=1,
        x0=100.0, y0=100.0, x1=500.0, y1=300.0, text_reference="thermodynamics", section_title="S", provenance="EXPLICIT_CLASSIFIER"
    )
    db.add_all([ent, ev])
    db.commit()

    doc_repo = DocumentRepository(db)
    k_repo = KnowledgeRepository(db)
    retrieval_service = RetrievalService(k_repo, doc_repo, RankingWeights())

    # Unscoped retrieval (allowed_entity_ids is None)
    res = retrieval_service.retrieve(
        RetrievalRequest(
            query="Thermodynamics",
            scope=RetrievalScope(
                document_id=doc.id,
                version_id=k_version.id,
                allowed_entity_ids=None
            ),
            options=RetrievalOptions(strategy="LEXICAL", include_passages=True, include_evidence=True)
        )
    )

    assert len(res.entities) == 1
    assert len(res.entities[0].passages) == 1
    assert res.entities[0].passages[0].text == "Full textbook paragraph on thermodynamics."
    assert res.entities[0].passages[0].block_id == "blk_unscoped"


