import pytest
import os
import io
import time
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient
import pptx

from app.models.document import Base, Document, DocumentPage, DocumentBlock
from app.models.review import AcademicGraphSnapshot
from app.models.knowledge import KnowledgeVersion, KnowledgeEntity, KnowledgeEvidence, KnowledgeRelationship
from app.models.artifact import ArtifactJob
from app.schemas.academic import AcademicNodeCategory
from app.schemas.artifact import ArtifactJobCreate, ArtifactJobRead, ArtifactType, ArtifactStatus
from app.schemas.retrieval import RetrievalRequest, RetrievalScope, RetrievalOptions
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.artifact_repository import ArtifactRepository
from app.services.retrieval.retrieval_service import RetrievalService
from app.services.retrieval.passage_retriever import PassageRetriever, check_text_references_overlap
from app.services.retrieval.ranker import RankingWeights
from app.services.generation.mock_provider import MockLLMProvider
from app.services.generation.groq_provider import GroqProvider
from app.services.generation.errors import GroundingValidationError, LLMProviderError
from app.services.artifact.artifact_planner import (
    ArtifactPlanner,
    estimate_tokens,
    MAX_CONTEXT_TOKENS,
    MAX_TOTAL_CHUNKS,
)
from app.services.artifact.artifact_validator import ArtifactValidator, ArtifactValidationContext
from app.services.artifact.pptx_renderer import PPTXRenderer
from app.services.artifact.artifact_service import ArtifactService
from app.api.routes import artifact as artifact_route_module
from app.main import create_app
from app.db.session import get_db



from sqlalchemy.pool import StaticPool

@pytest.fixture
def isolated_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    SessionClass = sessionmaker(bind=engine)
    session = SessionClass()
    yield session
    session.close()


@pytest.fixture
def textbook_fixture(isolated_db: Session):
    """
    Realistic isolated textbook fixture with two substantive units, topics,
    and a mixed block with exclusively unselected markers.
    """
    doc_id = "doc_textbook_4"
    upload_id = "upl_textbook_4"

    doc = Document(
        id=doc_id,
        upload_id=upload_id,
        status="processed",
        review_state="APPROVED",
        extraction_timestamp=datetime.utcnow(),
        processing_time=2.0
    )
    isolated_db.add(doc)

    page1 = DocumentPage(id="page_tb_1", document_id=doc_id, page_number=1, width=612.0, height=792.0)
    page2 = DocumentPage(id="page_tb_2", document_id=doc_id, page_number=2, width=612.0, height=792.0)
    isolated_db.add_all([page1, page2])

    # Page 1 Blocks (Unit 1: Quantum Computing)
    blk_u1 = DocumentBlock(
        id="blk_u1",
        document_id=doc_id,
        page_id=page1.id,
        page_number=1,
        reading_order=1,
        block_type="HEADING",
        text="Unit 1: Quantum Computing and Information Theory.",
        x0=50.0, y0=50.0, x1=550.0, y1=100.0
    )
    blk_t1 = DocumentBlock(
        id="blk_t1",
        document_id=doc_id,
        page_id=page1.id,
        page_number=1,
        reading_order=2,
        block_type="PARAGRAPH",
        text="Quantum mechanics leverages superposition and entanglement to represent arbitrary states using qubits.",
        x0=50.0, y0=110.0, x1=550.0, y1=250.0
    )

    # Page 2 Blocks (Unit 2: Cellular Biology)
    blk_u2 = DocumentBlock(
        id="blk_u2",
        document_id=doc_id,
        page_id=page2.id,
        page_number=2,
        reading_order=1,
        block_type="HEADING",
        text="Unit 2: Cellular Respiration and Metabolic Pathways.",
        x0=50.0, y0=50.0, x1=550.0, y1=100.0
    )
    blk_t2 = DocumentBlock(
        id="blk_t2",
        document_id=doc_id,
        page_id=page2.id,
        page_number=2,
        reading_order=2,
        block_type="PARAGRAPH",
        text="Cellular respiration transforms biochemical energy from nutrients into adenosine triphosphate (ATP) molecules.",
        x0=50.0, y0=110.0, x1=550.0, y1=250.0
    )
    # Mixed block on page 2: contains verified selected Bio sentence and unselected Physics sentence
    blk_mixed = DocumentBlock(
        id="blk_mixed_2",
        document_id=doc_id,
        page_id=page2.id,
        page_number=2,
        reading_order=3,
        block_type="PARAGRAPH",
        text="The mitochondrial matrix hosts the tricarboxylic acid cycle. EXCLUSIVELY_UNSELECTED_MARKER_DARK_MATTER: Dark matter comprises 85 percent of cosmic matter.",
        x0=50.0, y0=260.0, x1=550.0, y1=400.0
    )

    isolated_db.add_all([blk_u1, blk_t1, blk_u2, blk_t2, blk_mixed])

    snapshot = AcademicGraphSnapshot(
        id="snap_tb_4",
        upload_id=upload_id,
        pipeline_run_id="run_tb_4",
        approval_version=1,
        approved_revision=1,
        base_graph_fingerprint="fp_tb_1",
        resolved_graph_fingerprint="fp_tb_2",
        reviewer_id="lead_reviewer",
        approval_timestamp=time.time(),
        nodes=[],
        edges=[]
    )
    k_version = KnowledgeVersion(
        id="kv_tb_4",
        upload_id=upload_id,
        snapshot_id=snapshot.id,
        status="FINALIZED"
    )
    isolated_db.add_all([snapshot, k_version])

    # Entities
    u1_ent = KnowledgeEntity(
        id="ent_u1",
        knowledge_version_id=k_version.id,
        title="Unit 1: Quantum Computing",
        entity_type="UNIT",
        content="Comprehensive exploration of quantum computational models and physical qubits.",
        stable_id="s_u1"
    )
    t1_ent = KnowledgeEntity(
        id="ent_t1",
        knowledge_version_id=k_version.id,
        title="Topic 1.1: Superposition and Entanglement",
        entity_type="TOPIC",
        content="Qubit state spaces and superposition principles in quantum information theory.",
        stable_id="s_t1"
    )
    u2_ent = KnowledgeEntity(
        id="ent_u2",
        knowledge_version_id=k_version.id,
        title="Unit 2: Cellular Respiration",
        entity_type="UNIT",
        content="Comprehensive exploration of cellular metabolic pathways and energy synthesis.",
        stable_id="s_u2"
    )
    t2_ent = KnowledgeEntity(
        id="ent_t2",
        knowledge_version_id=k_version.id,
        title="Topic 2.1: Mitochondrial Pathways",
        entity_type="TOPIC",
        content="Mitochondrial matrix respiration, ATP synthesis, and tricarboxylic acid cycle.",
        stable_id="s_t2"
    )
    isolated_db.add_all([u1_ent, t1_ent, u2_ent, t2_ent])

    # Evidence
    ev_u1 = KnowledgeEvidence(
        id="ev_u1",
        entity_id=u1_ent.id,
        document_id=doc_id,
        page_number=1,
        x0=50.0, y0=50.0, x1=550.0, y1=100.0,
        text_reference="Unit 1: Quantum Computing and Information Theory.",
        provenance="EXPLICIT_CLASSIFIER"
    )
    ev_t1 = KnowledgeEvidence(
        id="ev_t1",
        entity_id=t1_ent.id,
        document_id=doc_id,
        page_number=1,
        x0=50.0, y0=110.0, x1=550.0, y1=250.0,
        text_reference="Quantum mechanics leverages superposition and entanglement to represent arbitrary states using qubits.",
        provenance="EXPLICIT_CLASSIFIER"
    )
    ev_u2 = KnowledgeEvidence(
        id="ev_u2",
        entity_id=u2_ent.id,
        document_id=doc_id,
        page_number=2,
        x0=50.0, y0=50.0, x1=550.0, y1=100.0,
        text_reference="Unit 2: Cellular Respiration and Metabolic Pathways.",
        provenance="EXPLICIT_CLASSIFIER"
    )
    ev_t2 = KnowledgeEvidence(
        id="ev_t2",
        entity_id=t2_ent.id,
        document_id=doc_id,
        page_number=2,
        x0=50.0, y0=110.0, x1=550.0, y1=250.0,
        text_reference="Cellular respiration transforms biochemical energy from nutrients into adenosine triphosphate (ATP) molecules.",
        provenance="EXPLICIT_CLASSIFIER"
    )
    # Evidence for mixed block with isolated verified text reference
    ev_t2_mixed = KnowledgeEvidence(
        id="ev_t2_mixed",
        entity_id=t2_ent.id,
        document_id=doc_id,
        page_number=2,
        x0=50.0, y0=260.0, x1=550.0, y1=400.0,
        text_reference="The mitochondrial matrix hosts the tricarboxylic acid cycle.",
        provenance="EXPLICIT_CLASSIFIER"
    )
    isolated_db.add_all([ev_u1, ev_t1, ev_u2, ev_t2, ev_t2_mixed])

    # Relationships
    r1 = KnowledgeRelationship(
        id="rel_1",
        knowledge_version_id=k_version.id,
        source_entity_id=u1_ent.id,
        target_entity_id=t1_ent.id,
        relationship_type="CONTAINS"
    )
    r2 = KnowledgeRelationship(
        id="rel_2",
        knowledge_version_id=k_version.id,
        source_entity_id=u2_ent.id,
        target_entity_id=t2_ent.id,
        relationship_type="CONTAINS"
    )
    isolated_db.add_all([r1, r2])
    isolated_db.commit()

    return {
        "db": isolated_db,
        "upload_id": upload_id,
        "doc_id": doc_id,
        "kv_id": k_version.id,
        "u1_id": u1_ent.id,
        "t1_id": t1_ent.id,
        "u2_id": u2_ent.id,
        "t2_id": t2_ent.id,
        "ev_t2_mixed_id": ev_t2_mixed.id
    }


# =============================================================================
# 1. REAL INTERNAL PIPELINE ACCEPTANCE TEST
# =============================================================================
@pytest.mark.asyncio
async def test_acceptance_real_pipeline_selection_to_download(textbook_fixture):
    """
    Demonstrates the real internal pipeline without mocking compiler, selection resolver,
    retrieval service, planner, validator, or renderer:
    approved snapshot → compiled knowledge → persisted selection → scoped retrieval →
    planner → validator → PPTX renderer → completed job → download endpoint.
    Verified end-to-end through the production application factory (create_app)
    and the real production API prefix (/api/v1).
    """
    db = textbook_fixture["db"]
    upload_id = textbook_fixture["upload_id"]
    kv_id = textbook_fixture["kv_id"]
    u2_id = textbook_fixture["u2_id"]

    # 1. Initialize production application factory with dependency override for isolated storage only
    app = create_app()
    isolated_maker = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
    app.dependency_overrides[get_db] = lambda: isolated_maker()
    orig_bg_maker = artifact_route_module.background_session_maker
    artifact_route_module.background_session_maker = isolated_maker

    try:
        client = TestClient(app)

        # 2. Invoke real production POST endpoint to create and start artifact job
        create_payload = {
            "upload_id": upload_id,
            "knowledge_version_id": kv_id,
            "artifact_type": "PPTX",
            "config": {
                "selected_unit_ids": [u2_id],
                "include_examples": True,
                "include_questions": False,
                "audience_level": "intermediate",
                "provider": "mock"
            }
        }
        resp = client.post("/api/v1/artifacts/generate", json=create_payload)
        assert resp.status_code == 200, resp.text
        job_data = resp.json()
        job_id = job_data["id"]

        # Verify persisted configuration in response
        assert job_data["config"]["selected_unit_ids"] == [u2_id]
        assert job_data["config"]["document_id"] == textbook_fixture["doc_id"]

        # 3. Verify status through real production GET endpoint
        # Under TestClient, FastAPI BackgroundTasks run synchronously before client.post returns
        resp_status = client.get(f"/api/v1/artifacts/{job_id}")
        assert resp_status.status_code == 200
        job_status = resp_status.json()
        assert job_status["status"] == "COMPLETED"
        assert job_status["artifact_uri"] is not None
        assert Path(job_status["artifact_uri"]).exists()

        # Validated plan persisted in DB
        assert job_status["plan"] is not None
        assert "slides" in job_status["plan"]
        assert len(job_status["plan"]["slides"]) >= 2

        # 4. Verify Download Endpoint Returns Valid PPTX Bytes through real route
        resp_dl = client.get(f"/api/v1/artifacts/{job_id}/download")
        assert resp_dl.status_code == 200
        assert resp_dl.headers["content-type"] == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        assert f"artifact_{job_id}.pptx" in resp_dl.headers["content-disposition"]

        # 5. Reopen downloaded bytes with python-pptx
        downloaded_bytes = io.BytesIO(resp_dl.content)
        prs = pptx.Presentation(downloaded_bytes)
        assert len(prs.slides) >= 2
        # Verify slide dimensions are explicit widescreen 16:9
        assert abs(prs.slide_width.inches - 13.333) < 0.01
        assert abs(prs.slide_height.inches - 7.5) < 0.01

        # 6. Check substantive content in slide BODIES (not only titles or speaker notes)
        all_slide_text = ""
        body_text = ""
        for slide in prs.slides:
            if slide.shapes.title and slide.shapes.title.text:
                all_slide_text += slide.shapes.title.text + " "
            for shape in slide.shapes:
                if shape != slide.shapes.title and shape.has_text_frame:
                    body_text += shape.text_frame.text + " "
                    all_slide_text += shape.text_frame.text + " "
            if slide.notes_slide and slide.notes_slide.notes_text_frame:
                all_slide_text += slide.notes_slide.notes_text_frame.text + " "

        # Substantive selected content MUST appear in slide bodies
        assert any(term in body_text for term in ["ATP", "adenosine triphosphate", "Cellular respiration", "metabolic"]), \
            f"Expected substantive content in slide bodies, got: {body_text}"
        assert "Cellular Respiration" in all_slide_text or "Unit 2" in all_slide_text

        # Unselected Unit 1 content and exclusively unselected markers MUST BE ABSENT
        assert "EXCLUSIVELY_UNSELECTED_MARKER_DARK_MATTER" not in all_slide_text
        assert "Quantum Computing" not in all_slide_text
        assert "qubits" not in all_slide_text.lower()

        # 7. Retain one explicitly labelled test artifact outside development artifact storage
        test_artifact_dir = Path("data/test_artifacts")
        test_artifact_dir.mkdir(parents=True, exist_ok=True)
        fixture_artifact_path = test_artifact_dir / "phase4_acceptance_artifact.pptx"
        fixture_artifact_path.write_bytes(resp_dl.content)
        assert fixture_artifact_path.exists()
        assert fixture_artifact_path.stat().st_size > 0

    finally:
        artifact_route_module.background_session_maker = orig_bg_maker
        # Clean up rendered working artifact in data/artifacts
        out_path = Path("data/artifacts") / f"artifact_{job_id}.pptx"
        if out_path.exists():
            out_path.unlink()


# =============================================================================
# 2. AMBIGUOUS PROVENANCE REGRESSIONS
# =============================================================================
def test_partial_overlapping_references_detection():
    """Verify check_text_references_overlap detects partial overlap and span overlap."""
    # Prefix/suffix overlap
    ref1 = "Introduction to cellular biology and metabolic pathways"
    ref2 = "metabolic pathways in eukaryotic cells and mitochondria"
    assert check_text_references_overlap(ref1, ref2) is True

    # Complete containment
    assert check_text_references_overlap("cellular biology", "advanced cellular biology concepts") is True

    # Disjoint references
    assert check_text_references_overlap("Quantum physics principles", "Mitochondrial matrix biology") is False

    # Block text span overlap
    block_text = "The quick brown fox jumps over the lazy dog"
    assert check_text_references_overlap("brown fox", "fox jumps", block_text=block_text) is True
    assert check_text_references_overlap("quick brown", "lazy dog", block_text=block_text) is False


def _create_test_version(db, suffix: str) -> KnowledgeVersion:
    upload_id = f"upl_{suffix}"
    doc = Document(
        id=f"doc_{suffix}",
        upload_id=upload_id,
        status="processed",
        review_state="APPROVED",
        extraction_timestamp=datetime.utcnow(),
        processing_time=1.0
    )
    snap = AcademicGraphSnapshot(
        id=f"snap_{suffix}",
        upload_id=upload_id,
        pipeline_run_id=f"run_{suffix}",
        approval_version=1,
        approved_revision=1,
        base_graph_fingerprint=f"fp1_{suffix}",
        resolved_graph_fingerprint=f"fp2_{suffix}",
        reviewer_id="reviewer",
        approval_timestamp=time.time(),
        nodes=[],
        edges=[]
    )
    v = KnowledgeVersion(
        id=f"kv_{suffix}",
        upload_id=upload_id,
        snapshot_id=snap.id,
        status="BUILDING"
    )
    db.add_all([doc, snap, v])
    return v


def test_cross_scope_identical_text_ambiguity_excluded_without_area_bias(textbook_fixture):
    """
    Verify that when multiple cross-scope candidate blocks match identical text reference
    and exact block ID is NOT available, it is excluded with CROSS_SCOPE_AMBIGUITY.
    Geometry / area must NOT establish ownership.
    """
    db = textbook_fixture["db"]
    doc_id = textbook_fixture["doc_id"]
    k_repo = KnowledgeRepository(db)
    d_repo = DocumentRepository(db)

    # Create two blocks on page 10 with identical text reference
    p10 = DocumentPage(id="page_10", document_id=doc_id, page_number=10, width=612.0, height=792.0)
    b1 = DocumentBlock(
        id="blk_cand_1", document_id=doc_id, page_id=p10.id, page_number=10, reading_order=1,
        block_type="PARAGRAPH", text="Repeated identical paragraph content appearing in multiple sections.",
        x0=50.0, y0=50.0, x1=550.0, y1=150.0
    )
    b2 = DocumentBlock(
        id="blk_cand_2", document_id=doc_id, page_id=p10.id, page_number=10, reading_order=2,
        block_type="PARAGRAPH", text="Repeated identical paragraph content appearing in multiple sections.",
        x0=50.0, y0=160.0, x1=550.0, y1=300.0  # Larger area!
    )
    db.add_all([p10, b1, b2])

    # Create a dedicated KnowledgeVersion and entity for ambiguity testing
    v_ambig = _create_test_version(db, "ambig")
    ent_ambig = KnowledgeEntity(id="ent_ambig", knowledge_version_id=v_ambig.id, title="Ambig Topic", entity_type="TOPIC", content="Substantive ambiguity topic content.", stable_id="s_ambig")
    db.add(ent_ambig)

    # Evidence overlapping both b1 and b2 geometrically
    ev = KnowledgeEvidence(
        id="ev_ambig_test",
        entity_id=ent_ambig.id,
        document_id=doc_id,
        page_number=10,
        x0=50.0, y0=50.0, x1=550.0, y1=300.0,  # Overlaps both
        text_reference="Repeated identical paragraph content appearing in multiple sections.",
        provenance="EXPLICIT_CLASSIFIER",
        metadata_json={}  # No exact block ID!
    )
    db.add(ev)
    db.flush()
    v_ambig.status = "FINALIZED"
    db.commit()

    retriever = PassageRetriever(d_repo, k_repo)
    scope = MagicMock()
    scope.document_id = doc_id
    scope.version_id = v_ambig.id
    scope.allowed_entity_ids = [ent_ambig.id]

    from app.services.retrieval.evidence_retriever import EvidenceCandidate
    cand = EvidenceCandidate(evidence=ev, entity_id=ev.entity_id, is_stale=False)

    passages = retriever.retrieve_passages([cand], scope)
    # Must be EXCLUDED with CROSS_SCOPE_AMBIGUITY, not chosen by largest area!
    assert len(passages) == 0
    assert any("CROSS_SCOPE_AMBIGUITY" in d for d in retriever.diagnostics)


def test_cross_scope_disambiguated_by_exact_provenance(textbook_fixture):
    """
    Verify that exact block ID provenance successfully disambiguates multiple candidate blocks.
    """
    db = textbook_fixture["db"]
    doc_id = textbook_fixture["doc_id"]
    k_repo = KnowledgeRepository(db)
    d_repo = DocumentRepository(db)

    # Create two candidate blocks on page 10
    p10 = DocumentPage(id="page_10_exact", document_id=doc_id, page_number=10, width=612.0, height=792.0)
    b1 = DocumentBlock(
        id="blk_cand_1", document_id=doc_id, page_id=p10.id, page_number=10, reading_order=1,
        block_type="PARAGRAPH", text="Repeated identical paragraph content appearing in multiple sections.",
        x0=50.0, y0=50.0, x1=550.0, y1=150.0
    )
    b2 = DocumentBlock(
        id="blk_cand_2", document_id=doc_id, page_id=p10.id, page_number=10, reading_order=2,
        block_type="PARAGRAPH", text="Repeated identical paragraph content appearing in multiple sections.",
        x0=50.0, y0=160.0, x1=550.0, y1=300.0
    )
    db.add_all([p10, b1, b2])

    # Create a dedicated KnowledgeVersion and entity for exact provenance test
    v_exact = _create_test_version(db, "exact")
    ent_exact = KnowledgeEntity(id="ent_exact", knowledge_version_id=v_exact.id, title="Exact Topic", entity_type="TOPIC", content="Substantive exact topic content.", stable_id="s_exact")
    db.add(ent_exact)

    # Evidence with explicit block_id in metadata
    ev = KnowledgeEvidence(
        id="ev_exact_prov_test",
        entity_id=ent_exact.id,
        document_id=doc_id,
        page_number=10,
        x0=50.0, y0=50.0, x1=550.0, y1=300.0,
        text_reference="Repeated identical paragraph content appearing in multiple sections.",
        provenance="EXPLICIT_CLASSIFIER",
        metadata_json={"block_id": "blk_cand_1"}  # Exact block reference!
    )
    db.add(ev)
    db.flush()
    v_exact.status = "FINALIZED"
    db.commit()

    retriever = PassageRetriever(d_repo, k_repo)
    scope = MagicMock()
    scope.document_id = doc_id
    scope.version_id = v_exact.id
    scope.allowed_entity_ids = [ent_exact.id]

    from app.services.retrieval.evidence_retriever import EvidenceCandidate
    cand = EvidenceCandidate(evidence=ev, entity_id=ev.entity_id, is_stale=False)

    passages = retriever.retrieve_passages([cand], scope)
    assert len(passages) == 1
    assert passages[0].block_id == "blk_cand_1"


# =============================================================================
# 3. MISSING SUBSTANTIVE EVIDENCE REGRESSIONS
# =============================================================================
@pytest.mark.asyncio
async def test_empty_retrieval_without_diagnostics_fails(textbook_fixture):
    """
    Verify that an empty retrieval result without any exclusion diagnostics
    halts before provider invocation with GroundingValidationError identifying
    the affected container.
    """
    db = textbook_fixture["db"]
    k_repo = KnowledgeRepository(db)
    d_repo = DocumentRepository(db)

    # Create a dedicated KnowledgeVersion with an entity having empty/trivial content
    v_empty = _create_test_version(db, "empty")
    ent_empty = KnowledgeEntity(
        id="ent_empty_u2",
        knowledge_version_id=v_empty.id,
        title="Unit 2: Cellular Respiration",
        entity_type="UNIT",
        content="",  # Empty content to test retrieval sufficiency
        stable_id="s_empty_u2"
    )
    db.add(ent_empty)
    db.flush()
    v_empty.status = "FINALIZED"
    db.commit()

    # Mock retrieval service returning empty entities without diagnostics
    from app.schemas.retrieval import RetrievalResult, RetrievalProvenance
    empty_result = RetrievalResult(
        query="empty",
        scope=RetrievalScope(document_id=textbook_fixture["doc_id"], version_id=v_empty.id),
        provenance=RetrievalProvenance(knowledge_version_id=v_empty.id, approval_version=1, document_id=textbook_fixture["doc_id"], strategy_used="LEXICAL", total_candidates_considered=0),
        entities=[],
        total_entity_count=0,
        has_more=False,
        diagnostics=[]
    )
    mock_retrieval_svc = MagicMock()
    mock_retrieval_svc.retrieve.return_value = empty_result

    mock_provider = MockLLMProvider()
    planner = ArtifactPlanner(k_repo, mock_retrieval_svc, mock_provider)

    job_read = ArtifactJobRead(
        id="job_empty_test",
        upload_id=v_empty.upload_id,
        knowledge_version_id=v_empty.id,
        artifact_type=ArtifactType.PPTX,
        status="PLANNING",
        config={"selected_unit_ids": [ent_empty.id]},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    with pytest.raises(GroundingValidationError) as exc:
        await planner.plan(job_read)

    # Must halt before provider invocation
    assert len(mock_provider.calls) == 0
    assert "Unit 2: Cellular Respiration" in str(exc.value)
    assert "no usable substantive evidence" in str(exc.value)


# =============================================================================
# 4. PROVIDER CONFIGURATION & STRUCTURED OUTPUT
# =============================================================================
@pytest.mark.asyncio
async def test_missing_live_provider_configuration_raises_explicit_failure(textbook_fixture):
    """
    Verify that missing live provider configuration (no GROQ_API_KEY) raises
    an explicit configuration failure and does NOT silently fall back to mock.
    """
    db = textbook_fixture["db"]
    service = ArtifactService(db)

    # Job created without explicit mock provider config
    job_create = ArtifactJobCreate(
        upload_id=textbook_fixture["upload_id"],
        knowledge_version_id=textbook_fixture["kv_id"],
        artifact_type=ArtifactType.PPTX,
        config={"selected_unit_ids": [textbook_fixture["u2_id"]]}  # No provider="mock"!
    )
    job = service.create_artifact_job(job_create)

    # Ensure GROQ_API_KEY is unset/empty
    with patch("app.core.config.settings.GROQ_API_KEY", None):
        with patch.dict(os.environ, {"LLM_PROVIDER": ""}, clear=False):
            await service.run_generation_pipeline(job.id)

    updated_job = service.get_job_status(job.id)
    assert updated_job.status == ArtifactStatus.FAILED
    assert "Missing live provider configuration" in updated_job.error_message
    assert updated_job.artifact_uri is None


@pytest.mark.asyncio
async def test_provider_malformed_json_schema_fails_cleanly(textbook_fixture):
    """
    Verify that malformed JSON or invalid schema from provider causes job failure
    at [PLANNING] without producing partial files.
    """
    db = textbook_fixture["db"]
    service = ArtifactService(db)

    job_create = ArtifactJobCreate(
        upload_id=textbook_fixture["upload_id"],
        knowledge_version_id=textbook_fixture["kv_id"],
        artifact_type=ArtifactType.PPTX,
        config={
            "selected_unit_ids": [textbook_fixture["u2_id"]],
            "provider": "mock",
            "mock_scenario": "malformed_output"
        }
    )
    job = service.create_artifact_job(job_create)

    await service.run_generation_pipeline(job.id)

    updated_job = service.get_job_status(job.id)
    assert updated_job.status == ArtifactStatus.FAILED
    assert "[PLANNING]" in updated_job.error_message
    assert updated_job.artifact_uri is None


@pytest.mark.asyncio
async def test_provider_fabricated_citations_rejected_by_planner(textbook_fixture):
    """
    Verify that fabricated source_node_ids returned by provider are strictly rejected.
    """
    db = textbook_fixture["db"]
    service = ArtifactService(db)

    job_create = ArtifactJobCreate(
        upload_id=textbook_fixture["upload_id"],
        knowledge_version_id=textbook_fixture["kv_id"],
        artifact_type=ArtifactType.PPTX,
        config={
            "selected_unit_ids": [textbook_fixture["u2_id"]],
            "provider": "mock",
            "mock_scenario": "invalid_citation"
        }
    )
    job = service.create_artifact_job(job_create)

    await service.run_generation_pipeline(job.id)

    updated_job = service.get_job_status(job.id)
    assert updated_job.status == ArtifactStatus.FAILED
    assert "Fabricated source_node_id" in updated_job.error_message


@pytest.mark.asyncio
async def test_provider_timeout_and_rate_limit_handled(textbook_fixture):
    """
    Verify that rate-limit and timeout errors from provider fail gracefully.
    """
    db = textbook_fixture["db"]
    service = ArtifactService(db)

    for scenario in ("timeout", "rate_limit"):
        job_create = ArtifactJobCreate(
            upload_id=textbook_fixture["upload_id"],
            knowledge_version_id=textbook_fixture["kv_id"],
            artifact_type=ArtifactType.PPTX,
            config={
                "selected_unit_ids": [textbook_fixture["u2_id"]],
                "provider": "mock",
                "mock_scenario": scenario
            }
        )
        job = service.create_artifact_job(job_create)
        await service.run_generation_pipeline(job.id)

        updated_job = service.get_job_status(job.id)
        assert updated_job.status == ArtifactStatus.FAILED
        assert "[PLANNING]" in updated_job.error_message


# =============================================================================
# 5. WORKLOAD LIMITS, CHUNKING SUBDIVISION & LIFECYCLE RECOVERY
# =============================================================================
@pytest.mark.asyncio
async def test_oversized_topic_subdivided_into_multiple_bounded_requests(textbook_fixture):
    """
    Demonstrate that a topic exceeding one chunk's capacity is subdivided into bounded
    segments while preserving:
    - Source order
    - Selected-container membership
    - Evidence associations
    - Hierarchy context
    - All source material scheduled for planning
    Does NOT reject normal long topics; instead, executes multiple bounded provider requests.
    """
    db = textbook_fixture["db"]
    k_repo = KnowledgeRepository(db)
    d_repo = DocumentRepository(db)
    retrieval_service = RetrievalService(k_repo, d_repo, RankingWeights())
    provider = MockLLMProvider()
    planner = ArtifactPlanner(k_repo, retrieval_service, provider)

    # 1. Create a KnowledgeVersion with an oversized topic (~15,000 chars, ~4700 tokens > single chunk capacity)
    v_sub = _create_test_version(db, "subdiv")
    unit_ent = KnowledgeEntity(
        id="ent_unit_subdiv",
        knowledge_version_id=v_sub.id,
        title="Unit: Advanced Molecular Genetics",
        entity_type="UNIT",
        content="Overview of advanced molecular mechanisms.",
        stable_id="s_unit_subdiv"
    )
    # Long text with paragraph breaks
    p1 = "Paragraph 1: DNA replication initiates at specific replication origins where helicase unwinds double strands.\n\n"
    p2 = "Paragraph 2: RNA primase synthesizes short RNA primers required by DNA polymerase for extension.\n\n"
    p3 = "Paragraph 3: Okazaki fragments on the lagging strand are joined together by DNA ligase enzyme.\n\n"
    long_content = (p1 + p2 + p3) * 60  # ~18,540 characters > MAX_CONTEXT_CHARS

    
    topic_ent = KnowledgeEntity(
        id="ent_topic_subdiv",
        knowledge_version_id=v_sub.id,
        title="Topic: DNA Replication Machinery",
        entity_type="TOPIC",
        content=long_content,
        stable_id="s_topic_subdiv"
    )
    db.add_all([unit_ent, topic_ent])

    # Add evidence association for the topic referencing the exact Document.id
    ev = KnowledgeEvidence(
        id="ev_subdiv_topic",
        entity_id=topic_ent.id,
        document_id=f"doc_subdiv",
        page_number=1,
        x0=50.0, y0=50.0, x1=550.0, y1=300.0,
        text_reference="DNA replication initiates at specific replication origins",
        provenance="EXPLICIT_CLASSIFIER"
    )
    rel = KnowledgeRelationship(
        id="rel_subdiv",
        knowledge_version_id=v_sub.id,
        source_entity_id=unit_ent.id,
        target_entity_id=topic_ent.id,
        relationship_type="CONTAINS"
    )
    db.add_all([ev, rel])
    db.flush()
    v_sub.status = "FINALIZED"
    db.commit()

    job_read = ArtifactJobRead(
        id="job_subdiv_test",
        upload_id=v_sub.upload_id,
        knowledge_version_id=v_sub.id,
        artifact_type=ArtifactType.PPTX,
        status="PLANNING",
        config={"selected_unit_ids": [unit_ent.id]},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    # 2. Plan artifact
    presentation_plan = await planner.plan(job_read)

    # 3. Assertions:
    # A. Topic was not rejected; multiple bounded provider requests were executed
    assert len(provider.calls) >= 2, f"Expected multiple bounded provider calls, got {len(provider.calls)}"
    
    # B. Slides generated for each part preserving source order
    slide_titles = [s.title for s in presentation_plan.slides]
    assert any("Part 1" in t for t in slide_titles)
    assert any("Part 2" in t for t in slide_titles)

    # C. Container hierarchy preserved (slides belong to Advanced Molecular Genetics)
    for slide in presentation_plan.slides:
        assert "Advanced Molecular Genetics" in slide.title or "DNA Replication" in slide.title

    # D. Evidence association preserved (citation node IDs reference the original entity)
    all_source_nodes = []
    for slide in presentation_plan.slides:
        all_source_nodes.extend(slide.source_node_ids)
    assert topic_ent.id in all_source_nodes



@pytest.mark.asyncio
async def test_oversized_job_exceeding_total_chunk_budget_fails_actionably(textbook_fixture):
    """
    Verify that an excessively large job exceeding MAX_TOTAL_CHUNKS (50 chunks)
    raises GroundingValidationError with an actionable message.
    """
    db = textbook_fixture["db"]
    k_repo = KnowledgeRepository(db)
    d_repo = DocumentRepository(db)
    retrieval_service = RetrievalService(k_repo, d_repo, RankingWeights())
    provider = MockLLMProvider()
    planner = ArtifactPlanner(k_repo, retrieval_service, provider)

    v_gigantic = _create_test_version(db, "gigantic")
    # Create 55 unit entities (exceeding MAX_TOTAL_CHUNKS = 50)
    entities = []
    for i in range(55):
        e = KnowledgeEntity(
            id=f"ent_gigantic_{i}",
            knowledge_version_id=v_gigantic.id,
            title=f"Unit {i}: Extensive Topic Material",
            entity_type="UNIT",
            content=f"Substantive content for unit {i} describing fundamental principles.",
            stable_id=f"s_gigantic_{i}"
        )
        entities.append(e)
    db.add_all(entities)
    db.flush()
    v_gigantic.status = "FINALIZED"
    db.commit()

    job_read = ArtifactJobRead(
        id="job_gigantic_test",
        upload_id=v_gigantic.upload_id,
        knowledge_version_id=v_gigantic.id,
        artifact_type=ArtifactType.PPTX,
        status="PLANNING",
        config={"selected_unit_ids": [e.id for e in entities]},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    # Temporarily set MAX_ENTITIES_PER_CHUNK to 1 so 55 entities require 55 chunks (> MAX_TOTAL_CHUNKS)
    with patch("app.services.artifact.artifact_planner.MAX_ENTITIES_PER_CHUNK", 1):
        with pytest.raises(GroundingValidationError) as exc:
            await planner.plan(job_read)
        assert "exceeds maximum supported limit (50 chunks)" in str(exc.value)
        assert "Please select fewer units" in str(exc.value)


@pytest.mark.asyncio
async def test_atomic_job_claiming_two_concurrent_sessions(textbook_fixture):
    """
    Verify atomic conditional state transition for job claiming:
    Two independent database sessions attempt to claim the same PENDING job concurrently.
    Exactly one execution wins and claims the job (PENDING -> PLANNING).
    The losing execution receives None, and run_generation_pipeline immediately
    aborts without calling provider or renderer.
    """
    db = textbook_fixture["db"]
    engine = db.get_bind()
    
    # Create two independent sessions pointing to the same database
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session1 = session_factory()
    session2 = session_factory()

    try:
        # Create a PENDING job in session1
        repo1 = ArtifactRepository(session1)
        job_create = ArtifactJobCreate(
            upload_id=textbook_fixture["upload_id"],
            knowledge_version_id=textbook_fixture["kv_id"],
            artifact_type=ArtifactType.PPTX,
            config={
                "selected_unit_ids": [textbook_fixture["u2_id"]],
                "provider": "mock"
            }
        )
        job = repo1.create_job(job_create)
        assert job.status == ArtifactStatus.PENDING.value

        # Session 1 and Session 2 both attempt to atomically claim the job
        repo2 = ArtifactRepository(session2)
        claim1 = repo1.claim_job_for_planning(job.id)
        claim2 = repo2.claim_job_for_planning(job.id)

        # Assert exactly one session claimed the job
        assert claim1 is not None, "Winning session must claim the job"
        assert claim1.status == ArtifactStatus.PLANNING.value
        assert claim2 is None, "Losing session must receive None on atomic conditional update"

        # Assert losing execution rejects pipeline without executing
        service2 = ArtifactService(session2)
        with patch("app.services.artifact.artifact_planner.ArtifactPlanner.plan") as mock_plan:
            with patch("app.services.artifact.pptx_renderer.PPTXRenderer.render") as mock_render:
                await service2.run_generation_pipeline(job.id)
                mock_plan.assert_not_called()
                mock_render.assert_not_called()

        # Create a fresh PENDING job to verify winning execution completes normally through pipeline
        job_create2 = ArtifactJobCreate(
            upload_id=textbook_fixture["upload_id"],
            knowledge_version_id=textbook_fixture["kv_id"],
            artifact_type=ArtifactType.PPTX,
            config={
                "selected_unit_ids": [textbook_fixture["u2_id"]],
                "provider": "mock"
            }
        )
        job2 = repo1.create_job(job_create2)
        service1 = ArtifactService(session1)
        await service1.run_generation_pipeline(job2.id)
        final_job = repo1.get_job(job2.id)
        assert final_job.status == ArtifactStatus.COMPLETED.value
        
        # Clean up
        if final_job.artifact_uri and Path(final_job.artifact_uri).exists():
            Path(final_job.artifact_uri).unlink()
    finally:
        session1.close()
        session2.close()


def test_offline_recover_jobs_cli_and_service(textbook_fixture):
    """
    Verify offline job recovery:
    1. Covers stranded PENDING as well as PLANNING and RENDERING jobs when include_pending=True.
    2. Transitions stranded jobs to FAILED with explicit actionable explanation.
    3. Leaves COMPLETED jobs and completed artifact files completely untouched.
    4. CLI runner app.services.artifact.recover_jobs supports --dry-run and --include-pending.
    """
    db = textbook_fixture["db"]
    service = ArtifactService(db)

    # Create dummy completed artifact file
    artifacts_dir = Path("data/artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    completed_file = artifacts_dir / "artifact_job_completed_safe.pptx"
    completed_file.write_bytes(b"EXISTING_VALID_PPTX_BYTES")

    # Insert simulated jobs
    job_pending = ArtifactJob(
        id="job_stranded_pending",
        upload_id=textbook_fixture["upload_id"],
        knowledge_version_id=textbook_fixture["kv_id"],
        artifact_type="PPTX",
        status=ArtifactStatus.PENDING.value,
        config={}
    )
    job_planning = ArtifactJob(
        id="job_stranded_plan",
        upload_id=textbook_fixture["upload_id"],
        knowledge_version_id=textbook_fixture["kv_id"],
        artifact_type="PPTX",
        status=ArtifactStatus.PLANNING.value,
        config={}
    )
    job_rendering = ArtifactJob(
        id="job_stranded_render",
        upload_id=textbook_fixture["upload_id"],
        knowledge_version_id=textbook_fixture["kv_id"],
        artifact_type="PPTX",
        status=ArtifactStatus.RENDERING.value,
        config={}
    )
    job_completed = ArtifactJob(
        id="job_completed_safe",
        upload_id=textbook_fixture["upload_id"],
        knowledge_version_id=textbook_fixture["kv_id"],
        artifact_type="PPTX",
        status=ArtifactStatus.COMPLETED.value,
        artifact_uri=str(completed_file),
        config={}
    )
    db.add_all([job_pending, job_planning, job_rendering, job_completed])
    db.commit()

    try:
        # 1. Test recover_interrupted_jobs without include_pending (recovers PLANNING and RENDERING only)
        recovered_default = service.recover_interrupted_jobs(include_pending=False)
        assert recovered_default == 2
        
        j_plan = service.get_job_status("job_stranded_plan")
        j_render = service.get_job_status("job_stranded_render")
        j_pend = service.get_job_status("job_stranded_pending")
        j_comp = service.get_job_status("job_completed_safe")

        assert j_plan.status == ArtifactStatus.FAILED
        assert j_render.status == ArtifactStatus.FAILED
        assert j_pend.status == ArtifactStatus.PENDING  # Untouched without include_pending
        assert j_comp.status == ArtifactStatus.COMPLETED  # Untouched

        # 2. Test recover_interrupted_jobs with include_pending=True (recovers stranded PENDING)
        recovered_pending = service.recover_interrupted_jobs(include_pending=True)
        assert recovered_pending == 1
        j_pend = service.get_job_status("job_stranded_pending")
        assert j_pend.status == ArtifactStatus.FAILED
        assert "interrupted while in PENDING stage" in j_pend.error_message

        # 3. Assert completed artifact file remained completely untouched
        assert completed_file.exists()
        assert completed_file.read_bytes() == b"EXISTING_VALID_PPTX_BYTES"

        # 4. Test CLI runner in recover_jobs.py
        import app.services.artifact.recover_jobs as recover_module
        with patch.object(recover_module, "SessionLocal", return_value=db):
            with patch("sys.argv", ["recover_jobs", "--dry-run", "--include-pending"]):
                recover_module.main()  # Must execute cleanly without error
    finally:
        if completed_file.exists():
            completed_file.unlink()


@pytest.mark.asyncio
async def test_renderer_failure_cleans_up_and_fails_job(textbook_fixture):
    """
    Verify that renderer failure cleans up any partial artifact file and marks job FAILED.
    """
    db = textbook_fixture["db"]
    service = ArtifactService(db)

    job_create = ArtifactJobCreate(
        upload_id=textbook_fixture["upload_id"],
        knowledge_version_id=textbook_fixture["kv_id"],
        artifact_type=ArtifactType.PPTX,
        config={
            "selected_unit_ids": [textbook_fixture["u2_id"]],
            "provider": "mock"
        }
    )
    job = service.create_artifact_job(job_create)

    with patch("app.services.artifact.pptx_renderer.PPTXRenderer.render", side_effect=IOError("Disk write failed")):
        await service.run_generation_pipeline(job.id)

    updated_job = service.get_job_status(job.id)
    assert updated_job.status == ArtifactStatus.FAILED
    assert "[RENDERING]" in updated_job.error_message
    assert updated_job.artifact_uri is None

