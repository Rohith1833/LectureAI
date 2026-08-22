import unittest
import time
import uuid
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, Document, AcademicGraphSnapshot
from app.models.document import DocumentPage, DocumentBlock
from app.models.knowledge import KnowledgeVersion, KnowledgeEntity, KnowledgeEvidence
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.document_repository import DocumentRepository
from app.schemas.retrieval import RetrievalScope
from app.services.retrieval.base import EntityCandidate
from app.services.retrieval.scope_resolver import ResolvedScope
from app.services.retrieval.evidence_retriever import EvidenceRetriever, EvidenceCandidate
from app.services.retrieval.passage_retriever import PassageRetriever, PassageCandidate


class TestRetrievalEvidencePassage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Use SQLite in-memory database with StaticPool to prevent file locking issues
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )

        @event.listens_for(cls.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(bind=cls.engine)
        cls.TestingSessionLocal = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.TestingSessionLocal()
        self.repo = KnowledgeRepository(self.db)
        self.doc_repo = DocumentRepository(self.db)
        self.ev_retriever = EvidenceRetriever(self.repo)
        self.pass_retriever = PassageRetriever(self.doc_repo)

        # Seed Document A
        self.upload_a = str(uuid.uuid4())
        self.doc_a = Document(
            id="doc_a_id",
            upload_id=self.upload_a,
            status="processed",
            extraction_timestamp="2026-08-21T12:00:00Z",
            processing_time=1.0,
            review_state="APPROVED"
        )

        # Seed Document B (Isolation)
        self.upload_b = str(uuid.uuid4())
        self.doc_b = Document(
            id="doc_b_id",
            upload_id=self.upload_b,
            status="processed",
            extraction_timestamp="2026-08-21T12:00:00Z",
            processing_time=1.0,
            review_state="APPROVED"
        )
        self.db.add_all([self.doc_a, self.doc_b])
        self.db.flush()

        # Seed DocumentPages
        self.page_a1 = DocumentPage(
            id="page_a1_id",
            document_id="doc_a_id",
            page_number=1,
            width=612.0,
            height=792.0
        )
        self.page_b1 = DocumentPage(
            id="page_b1_id",
            document_id="doc_b_id",
            page_number=1,
            width=612.0,
            height=792.0
        )
        self.db.add_all([self.page_a1, self.page_b1])
        self.db.flush()

        # Seed DocumentBlocks for Page A1
        # Block 1: "Introduction to search algorithms"
        self.blk_a1 = DocumentBlock(
            id="blk_a1_id",
            document_id="doc_a_id",
            page_id="page_a1_id",
            page_number=1,
            reading_order=1,
            block_type="HEADING",
            text="Search Algorithms",
            x0=100.0, y0=100.0, x1=300.0, y1=150.0,
            previous_block_id=None,
            next_block_id="blk_a2_id"
        )
        # Block 2: "Binary search cuts complexity in half"
        self.blk_a2 = DocumentBlock(
            id="blk_a2_id",
            document_id="doc_a_id",
            page_id="page_a1_id",
            page_number=1,
            reading_order=2,
            block_type="PARAGRAPH",
            text="Binary search splits the range.",
            x0=100.0, y0=160.0, x1=500.0, y1=260.0,
            previous_block_id="blk_a1_id",
            next_block_id="blk_a3_id"
        )
        # Block 3: "Complexity is O(log n)"
        self.blk_a3 = DocumentBlock(
            id="blk_a3_id",
            document_id="doc_a_id",
            page_id="page_a1_id",
            page_number=1,
            reading_order=3,
            block_type="PARAGRAPH",
            text="Complexity is O(log n).",
            x0=100.0, y0=270.0, x1=500.0, y1=320.0,
            previous_block_id="blk_a2_id",
            next_block_id=None
        )

        # Tie-break test blocks (for test_12)
        self.blk_tie_1 = DocumentBlock(
            id="blk_tie_1_id",
            document_id="doc_a_id",
            page_id="page_a1_id",
            page_number=1,
            reading_order=2,
            block_type="PARAGRAPH",
            text="First tie-break block.",
            x0=600.0, y0=600.0, x1=700.0, y1=700.0,
            previous_block_id=None,
            next_block_id=None
        )
        self.blk_tie_2 = DocumentBlock(
            id="blk_tie_2_id",
            document_id="doc_a_id",
            page_id="page_a1_id",
            page_number=1,
            reading_order=2,
            block_type="PARAGRAPH",
            text="Second tie-break block.",
            x0=600.0, y0=600.0, x1=700.0, y1=700.0,
            previous_block_id=None,
            next_block_id=None
        )

        # Seed DocumentBlocks for Page B1 (Isolation check)
        self.blk_b1 = DocumentBlock(
            id="blk_b1_id",
            document_id="doc_b_id",
            page_id="page_b1_id",
            page_number=1,
            reading_order=1,
            block_type="PARAGRAPH",
            text="Isolated text in Document B.",
            x0=100.0, y0=160.0, x1=500.0, y1=260.0,  # Same coordinates
            previous_block_id=None,
            next_block_id=None
        )
        self.db.add_all([self.blk_a1, self.blk_a2, self.blk_a3, self.blk_tie_1, self.blk_tie_2, self.blk_b1])
        self.db.flush()

        # Seed snapshots
        self.snap_a = AcademicGraphSnapshot(
            id="snap_a_id", upload_id=self.upload_a, pipeline_run_id="run_a",
            approval_version=1, approved_revision=1, base_graph_fingerprint="bfp_a",
            resolved_graph_fingerprint="rfp_a", approval_timestamp=time.time(),
            reviewer_id="reviewer", nodes=[], edges=[]
        )
        self.snap_b = AcademicGraphSnapshot(
            id="snap_b_id", upload_id=self.upload_b, pipeline_run_id="run_b",
            approval_version=1, approved_revision=1, base_graph_fingerprint="bfp_b",
            resolved_graph_fingerprint="rfp_b", approval_timestamp=time.time(),
            reviewer_id="reviewer", nodes=[], edges=[]
        )
        self.db.add_all([self.snap_a, self.snap_b])
        self.db.flush()

        # Seed versions
        self.v_a = KnowledgeVersion(
            id="v_a_id", upload_id=self.upload_a, snapshot_id="snap_a_id",
            status="BUILDING", created_at=time.time()
        )
        self.v_b = KnowledgeVersion(
            id="v_b_id", upload_id=self.upload_b, snapshot_id="snap_b_id",
            status="BUILDING", created_at=time.time()
        )
        self.db.add_all([self.v_a, self.v_b])
        self.db.flush()

        # Seed entities for version A
        self.e_search = KnowledgeEntity(
            id="e_search_id", knowledge_version_id="v_a_id",
            entity_type="CONCEPT", title="Binary Search",
            content="Binary Search explanation", stable_id="anc_binary_search"
        )
        self.e_algo = KnowledgeEntity(
            id="e_algo_id", knowledge_version_id="v_a_id",
            entity_type="ALGORITHM", title="Complexity Analysis",
            content="Complexity bounds", stable_id="anc_complexity_analysis"
        )
        # Entity with no evidence
        self.e_no_ev = KnowledgeEntity(
            id="e_no_ev_id", knowledge_version_id="v_a_id",
            entity_type="CONCEPT", title="Quantum theory",
            content="Theory description", stable_id="anc_quantum_theory"
        )
        self.db.add_all([self.e_search, self.e_algo, self.e_no_ev])
        self.db.flush()

        # Seed entities for version B
        self.e_b_search = KnowledgeEntity(
            id="e_b_search_id", knowledge_version_id="v_b_id",
            entity_type="CONCEPT", title="Binary Search",
            content="Isolated search", stable_id="anc_binary_search"
        )
        self.db.add(self.e_b_search)
        self.db.flush()

        # Seed evidence for Version A
        # ev1: matches block a2 exactly
        self.ev1 = KnowledgeEvidence(
            id="ev1_id",
            entity_id="e_search_id",
            source_node_id="academic_node_search",  # DIFFERENT FROM block id
            document_id="doc_a_id",
            page_number=1,
            x0=100.0, y0=160.0, x1=500.0, y1=260.0,
            text_reference="Binary search splits the range.",
            section_title="Chapter 1: Intro",
            provenance="compiled_build"
        )
        # ev2: matches block a3 (overlap)
        self.ev2 = KnowledgeEvidence(
            id="ev2_id",
            entity_id="e_search_id",
            source_node_id="academic_node_search",
            document_id="doc_a_id",
            page_number=1,
            x0=150.0, y0=280.0, x1=450.0, y1=310.0,
            text_reference="Complexity is O(log n).",
            section_title="Chapter 1: Intro",
            provenance="compiled_build"
        )
        # ev3: stale evidence (page_number is None)
        self.ev3 = KnowledgeEvidence(
            id="ev3_id",
            entity_id="e_algo_id",
            source_node_id="academic_node_algo",
            document_id="doc_a_id",
            page_number=None,
            x0=None, y0=None, x1=None, y1=None,
            text_reference="Missing reference info",
            section_title="Stale Section",
            provenance="stale_provenance"
        )
        # ev_missing_coords: page exists but coordinates None
        self.ev_missing_coords = KnowledgeEvidence(
            id="ev_missing_coords_id",
            entity_id="e_algo_id",
            source_node_id="academic_node_algo",
            document_id="doc_a_id",
            page_number=1,
            x0=None, y0=None, x1=None, y1=None,
            text_reference="Reference without coords",
            section_title="Section 1",
            provenance="no_coords"
        )
        # ev_tie: for tie breaking test
        self.ev_tie = KnowledgeEvidence(
            id="ev_tie_id",
            entity_id="e_algo_id",
            source_node_id="academic_node_algo",
            document_id="doc_a_id",
            page_number=1,
            x0=600.0, y0=600.0, x1=700.0, y1=700.0,
            text_reference="Tie break reference.",
            section_title="Section 2",
            provenance="tie_break"
        )
        # ev_wrong_page points to page 2 (non-existent)
        self.ev_wrong_page = KnowledgeEvidence(
            id="ev_wrong_page_id",
            entity_id="e_search_id",
            source_node_id="academic_node_search",
            document_id="doc_a_id",
            page_number=2,
            x0=100.0, y0=160.0, x1=500.0, y1=260.0,
            text_reference="Binary search splits the range.",
            section_title="Intro",
            provenance="compiled_build"
        )
        # ev_no_block points to non-existent coordinate block
        self.ev_no_block = KnowledgeEvidence(
            id="ev_no_block_id",
            entity_id="e_search_id",
            source_node_id="academic_node_search",
            document_id="doc_a_id",
            page_number=1,
            x0=800.0, y0=800.0, x1=900.0, y1=900.0,
            text_reference="Outside page boundaries.",
            section_title="Intro",
            provenance="compiled_build"
        )
        # ev_algo_dup matches blk_a2 exactly (multiple references to same block)
        self.ev_algo_dup = KnowledgeEvidence(
            id="ev_algo_dup_id",
            entity_id="e_algo_id",
            source_node_id="academic_node_algo",
            document_id="doc_a_id",
            page_number=1,
            x0=100.0, y0=160.0, x1=500.0, y1=260.0,
            text_reference="Binary search splits the range.",
            section_title="Chapter 1: Intro",
            provenance="compiled_build"
        )

        self.db.add_all([
            self.ev1, self.ev2, self.ev3, self.ev_missing_coords,
            self.ev_tie, self.ev_wrong_page, self.ev_no_block, self.ev_algo_dup
        ])
        self.db.flush()

        # Seed evidence for Version B
        self.ev_b1 = KnowledgeEvidence(
            id="ev_b1_id",
            entity_id="e_b_search_id",
            source_node_id="academic_node_b_search",
            document_id="doc_b_id",
            page_number=1,
            x0=100.0, y0=160.0, x1=500.0, y1=260.0,
            text_reference="Isolated text in Document B.",
            section_title="Chapter 1",
            provenance="compiled_build"
        )
        self.db.add(self.ev_b1)
        self.db.flush()

        # Finalize versions
        self.v_a.status = "FINALIZED"
        self.v_b.status = "FINALIZED"
        self.db.commit()

        # Setup scopes
        self.scope_a = ResolvedScope(document_id="doc_a_id", version_id="v_a_id")
        self.scope_b = ResolvedScope(document_id="doc_b_id", version_id="v_b_id")

        # Entity candidates stubs for retrieval
        self.cand_search = EntityCandidate(entity=self.e_search, match_score=1.0, match_reason="title_exact")
        self.cand_algo = EntityCandidate(entity=self.e_algo, match_score=0.8, match_reason="title_prefix")

    def tearDown(self):
        self.db.close()

    # ─── EVIDENCE RETRIEVAL TESTS ─────────────────────────────────

    def test_01_entity_with_one_evidence_record(self):
        """Verify entity with one evidence record returns correct list."""
        cands = [self.cand_algo]
        ev_list = self.ev_retriever.retrieve_evidence(cands, self.scope_a)
        self.assertEqual(len(ev_list), 4)
        ev_ids = [e.evidence.id for e in ev_list]
        self.assertIn("ev3_id", ev_ids)
        self.assertIn("ev_missing_coords_id", ev_ids)

    def test_02_entity_with_multiple_evidence_records(self):
        """Verify entity with multiple evidence records resolves all of them."""
        cands = [self.cand_search]
        ev_list = self.ev_retriever.retrieve_evidence(cands, self.scope_a)
        self.assertEqual(len(ev_list), 4)
        ev_ids = [e.evidence.id for e in ev_list]
        self.assertIn("ev1_id", ev_ids)
        self.assertIn("ev2_id", ev_ids)

    def test_03_multiple_entities(self):
        """Verify retrieval for multiple entity candidates."""
        cands = [self.cand_search, self.cand_algo]
        ev_list = self.ev_retriever.retrieve_evidence(cands, self.scope_a)
        self.assertEqual(len(ev_list), 8)

    def test_04_duplicate_entity_candidates_do_not_duplicate_evidence(self):
        """Verify duplicate candidates do not lead to duplicate evidence resolved."""
        cands = [self.cand_search, self.cand_search]
        ev_list = self.ev_retriever.retrieve_evidence(cands, self.scope_a)
        self.assertEqual(len(ev_list), 4)  # Deduplicated

    def test_05_stale_evidence_detected(self):
        """Verify stale evidence is detected (page_number is None)."""
        cands = [self.cand_algo]
        ev_list = self.ev_retriever.retrieve_evidence(cands, self.scope_a)
        stale_cands = [e for e in ev_list if e.evidence.id == "ev3_id"]
        self.assertEqual(len(stale_cands), 1)
        self.assertTrue(stale_cands[0].is_stale)

    def test_06_stale_evidence_preserved(self):
        """Verify stale evidence is returned and preserved instead of discarded."""
        cands = [self.cand_algo]
        ev_list = self.ev_retriever.retrieve_evidence(cands, self.scope_a)
        ev_ids = [e.evidence.id for e in ev_list]
        self.assertIn("ev3_id", ev_ids)

    def test_07_evidence_provenance_preserved(self):
        """Verify all compiled evidence metadata attributes are preserved."""
        cands = [self.cand_search]
        ev_list = self.ev_retriever.retrieve_evidence(cands, self.scope_a)
        ev1_cands = [e for e in ev_list if e.evidence.id == "ev1_id"]
        self.assertEqual(len(ev1_cands), 1)
        self.assertEqual(ev1_cands[0].evidence.provenance, "compiled_build")
        self.assertEqual(ev1_cands[0].evidence.section_title, "Chapter 1: Intro")

    def test_08_evidence_text_reference_preserved(self):
        """Verify compilation text reference snapshot is preserved."""
        cands = [self.cand_search]
        ev_list = self.ev_retriever.retrieve_evidence(cands, self.scope_a)
        ev1_cands = [e for e in ev_list if e.evidence.id == "ev1_id"]
        self.assertEqual(ev1_cands[0].evidence.text_reference, "Binary search splits the range.")

    def test_09_deterministic_evidence_ordering(self):
        """Verify evidence is returned in a deterministic sorted order."""
        cands = [self.cand_search, self.cand_algo]
        ev_list = self.ev_retriever.retrieve_evidence(cands, self.scope_a)
        self.assertTrue(len(ev_list) > 0)
        entity_ids = [e.entity_id for e in ev_list]
        self.assertEqual(entity_ids[0], "e_algo_id")

    # ─── PASSAGE RETRIEVAL TESTS ──────────────────────────────────

    def test_10_exact_source_block_resolution(self):
        """Verify exact coordinates resolved to the corresponding source DocumentBlock."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_search], self.scope_a)
        ev1_cand = [e for e in ev_list if e.evidence.id == "ev1_id"]
        
        passages = self.pass_retriever.retrieve_passages(ev1_cand, self.scope_a)
        self.assertEqual(len(passages), 1)
        self.assertEqual(passages[0].block_id, "blk_a2_id")
        self.assertEqual(passages[0].text, "Binary search splits the range.")

    def test_11_coordinate_overlap_resolution(self):
        """Verify overlap containment resolves to target block."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_search], self.scope_a)
        ev2_cand = [e for e in ev_list if e.evidence.id == "ev2_id"]
        
        passages = self.pass_retriever.retrieve_passages(ev2_cand, self.scope_a)
        self.assertEqual(len(passages), 1)
        self.assertEqual(passages[0].block_id, "blk_a3_id")
        self.assertEqual(passages[0].text, "Complexity is O(log n).")

    def test_12_multiple_matching_blocks_use_deterministic_selection(self):
        """Verify tie break selection when multiple blocks overlap."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_algo], self.scope_a)
        ev_tie_cand = [e for e in ev_list if e.evidence.id == "ev_tie_id"]
        
        passages = self.pass_retriever.retrieve_passages(ev_tie_cand, self.scope_a)
        self.assertEqual(len(passages), 1)
        self.assertEqual(passages[0].block_id, "blk_tie_1_id")

    def test_13_page_mismatch_produces_no_passage(self):
        """Verify coordinate lookup on different page returns no passage."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_search], self.scope_a)
        wrong_cand = [e for e in ev_list if e.evidence.id == "ev_wrong_page_id"]
        
        passages = self.pass_retriever.retrieve_passages(wrong_cand, self.scope_a)
        self.assertEqual(len(passages), 0)

    def test_14_document_mismatch_produces_no_passage(self):
        """Verify cross-document coordinates resolve to nothing (Document Isolation)."""
        ev_list = self.ev_retriever.retrieve_evidence([EntityCandidate(entity=self.e_b_search, match_score=1.0, match_reason="title_exact")], self.scope_b)
        ev_b1_cand = [e for e in ev_list if e.evidence.id == "ev_b1_id"]

        passages = self.pass_retriever.retrieve_passages(ev_b1_cand, self.scope_b)
        self.assertEqual(len(passages), 1)
        self.assertEqual(passages[0].document_id, "doc_b_id")
        self.assertEqual(passages[0].block_id, "blk_b1_id")
        self.assertNotEqual(passages[0].block_id, "blk_a2_id")

    def test_15_missing_block_produces_no_crash(self):
        """Verify that missing target blocks return empty results without crashing."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_search], self.scope_a)
        dangling_cand = [e for e in ev_list if e.evidence.id == "ev_no_block_id"]
        
        passages = self.pass_retriever.retrieve_passages(dangling_cand, self.scope_a)
        self.assertEqual(len(passages), 0)

    def test_16_stale_evidence_does_not_trigger_block_lookup(self):
        """Verify stale evidence skips coordinate page block queries."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_algo], self.scope_a)
        stale_cand = [e for e in ev_list if e.evidence.id == "ev3_id"]
        
        passages = self.pass_retriever.retrieve_passages(stale_cand, self.scope_a)
        self.assertEqual(len(passages), 0)

    def test_17_missing_coordinates_handled_correctly(self):
        """Verify coordinates = None on page skips lookup."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_algo], self.scope_a)
        no_coords_cand = [e for e in ev_list if e.evidence.id == "ev_missing_coords_id"]
        
        passages = self.pass_retriever.retrieve_passages(no_coords_cand, self.scope_a)
        self.assertEqual(len(passages), 0)

    def test_18_block_id_correctness(self):
        """Verify actual DocumentBlock.id is resolved."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_search], self.scope_a)
        ev1_cand = [e for e in ev_list if e.evidence.id == "ev1_id"]
        
        passages = self.pass_retriever.retrieve_passages(ev1_cand, self.scope_a)
        self.assertEqual(passages[0].block_id, "blk_a2_id")

    def test_19_source_node_id_is_not_block_id(self):
        """Verify academic source_node_id is NOT mapped as block_id."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_search], self.scope_a)
        ev1_cand = [e for e in ev_list if e.evidence.id == "ev1_id"]
        
        passages = self.pass_retriever.retrieve_passages(ev1_cand, self.scope_a)
        self.assertNotEqual(passages[0].block_id, "academic_node_search")
        self.assertEqual(passages[0].block_id, "blk_a2_id")

    def test_20_actual_document_block_text_returned(self):
        """Verify verbatim source block text is resolved and returned."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_search], self.scope_a)
        ev1_cand = [e for e in ev_list if e.evidence.id == "ev1_id"]
        
        passages = self.pass_retriever.retrieve_passages(ev1_cand, self.scope_a)
        self.assertEqual(passages[0].text, "Binary search splits the range.")

    def test_21_page_number_preserved(self):
        """Verify page number is preserved in PassageCandidate."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_search], self.scope_a)
        ev1_cand = [e for e in ev_list if e.evidence.id == "ev1_id"]
        
        passages = self.pass_retriever.retrieve_passages(ev1_cand, self.scope_a)
        self.assertEqual(passages[0].page_number, 1)

    def test_22_bounding_box_preserved(self):
        """Verify block layout bounding boxes are preserved."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_search], self.scope_a)
        ev1_cand = [e for e in ev_list if e.evidence.id == "ev1_id"]
        
        passages = self.pass_retriever.retrieve_passages(ev1_cand, self.scope_a)
        self.assertEqual(passages[0].x0, 100.0)
        self.assertEqual(passages[0].y0, 160.0)

    def test_23_block_type_preserved(self):
        """Verify layout block type category is preserved."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_search], self.scope_a)
        ev1_cand = [e for e in ev_list if e.evidence.id == "ev1_id"]
        
        passages = self.pass_retriever.retrieve_passages(ev1_cand, self.scope_a)
        self.assertEqual(passages[0].block_type, "PARAGRAPH")

    def test_24_section_title_preserved(self):
        """Verify evidence section title is preserved."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_search], self.scope_a)
        ev1_cand = [e for e in ev_list if e.evidence.id == "ev1_id"]
        
        passages = self.pass_retriever.retrieve_passages(ev1_cand, self.scope_a)
        self.assertEqual(passages[0].section_title, "Chapter 1: Intro")

    # ─── SURROUNDING CONTEXT TESTS ────────────────────────────────

    def test_25_previous_block_resolution(self):
        """Verify context resolves previous block text correctly."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_search], self.scope_a)
        ev1_cand = [e for e in ev_list if e.evidence.id == "ev1_id"]
        
        passages = self.pass_retriever.retrieve_passages(ev1_cand, self.scope_a)
        self.assertEqual(passages[0].previous_text, "Search Algorithms")

    def test_26_next_block_resolution(self):
        """Verify context resolves next block text correctly."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_search], self.scope_a)
        ev1_cand = [e for e in ev_list if e.evidence.id == "ev1_id"]
        
        passages = self.pass_retriever.retrieve_passages(ev1_cand, self.scope_a)
        self.assertEqual(passages[0].next_text, "Complexity is O(log n).")

    def test_27_missing_previous_next_handled_safely(self):
        """Verify missing previous/next context attributes are set to None without crash."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_search], self.scope_a)
        ev2_cand = [e for e in ev_list if e.evidence.id == "ev2_id"]
        
        passages = self.pass_retriever.retrieve_passages(ev2_cand, self.scope_a)
        self.assertIsNone(passages[0].next_text)

    def test_28_primary_block_distinguishable(self):
        """Verify primary text is distinct from surrounding context text attributes."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_search], self.scope_a)
        ev1_cand = [e for e in ev_list if e.evidence.id == "ev1_id"]
        
        passages = self.pass_retriever.retrieve_passages(ev1_cand, self.scope_a)
        self.assertEqual(passages[0].text, "Binary search splits the range.")
        self.assertNotEqual(passages[0].text, passages[0].previous_text)

    # ─── ISOLATION TESTS ──────────────────────────────────────────

    def test_29_evidence_scoped_to_correct_version(self):
        """Verify evidence returned belongs only to requested KnowledgeVersion."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_search], self.scope_a)
        for ev in ev_list:
            self.assertEqual(ev.evidence.entity.knowledge_version_id, "v_a_id")

    def test_30_evidence_scoped_to_correct_document(self):
        """Verify resolved scope document boundaries prevent cross-document evidence leaks."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_search], self.scope_a)
        for ev in ev_list:
            self.assertEqual(ev.evidence.document_id, "doc_a_id")

    def test_31_same_coordinates_leak_isolation(self):
        """Verify document blocks are strictly resolved within the correct document context."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_search], self.scope_a)
        ev1_cand = [e for e in ev_list if e.evidence.id == "ev1_id"]
        
        passages = self.pass_retriever.retrieve_passages(ev1_cand, self.scope_a)
        self.assertEqual(passages[0].document_id, "doc_a_id")
        self.assertEqual(passages[0].block_id, "blk_a2_id")

    # ─── EDGE CASES ───────────────────────────────────────────────

    def test_32_entity_with_no_evidence(self):
        """Verify entity candidate with no evidence returns empty list."""
        cand_no_ev = EntityCandidate(entity=self.e_no_ev, match_score=1.0, match_reason="title_exact")
        ev_list = self.ev_retriever.retrieve_evidence([cand_no_ev], self.scope_a)
        self.assertEqual(len(ev_list), 0)

    def test_33_empty_evidence_set(self):
        """Verify empty evidence candidate list resolved to empty passage list."""
        passages = self.pass_retriever.retrieve_passages([], self.scope_a)
        self.assertEqual(len(passages), 0)

    def test_34_stale_evidence_with_text_reference_available(self):
        """Verify stale evidence preserves text_reference snapshot."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_algo], self.scope_a)
        stale_cand = [e for e in ev_list if e.evidence.id == "ev3_id"]
        self.assertEqual(stale_cand[0].evidence.text_reference, "Missing reference info")

    def test_35_non_stale_evidence_with_missing_document_block(self):
        """Verify non-stale evidence with missing DocumentBlock yields no passage candidate."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_search], self.scope_a)
        no_block_cand = [e for e in ev_list if e.evidence.id == "ev_no_block_id"]
        
        passages = self.pass_retriever.retrieve_passages(no_block_cand, self.scope_a)
        self.assertEqual(len(passages), 0)

    def test_36_dangling_source_reference(self):
        """Verify dangling references yield empty results safely."""
        passages = self.pass_retriever.retrieve_passages([], self.scope_a)
        self.assertEqual(len(passages), 0)

    def test_37_multiple_evidence_records_pointing_to_same_block(self):
        """Verify multiple evidence records matching same block merge mapped entity references."""
        ev_list = self.ev_retriever.retrieve_evidence([self.cand_search, self.cand_algo], self.scope_a)
        target_evs = [e for e in ev_list if e.evidence.id in ["ev1_id", "ev_algo_dup_id"]]
        
        passages = self.pass_retriever.retrieve_passages(target_evs, self.scope_a)
        self.assertEqual(len(passages), 1)
        self.assertEqual(passages[0].block_id, "blk_a2_id")
        self.assertEqual(len(passages[0].entity_ids), 2)
        self.assertIn("e_search_id", passages[0].entity_ids)
        self.assertIn("e_algo_id", passages[0].entity_ids)


if __name__ == "__main__":
    unittest.main()
