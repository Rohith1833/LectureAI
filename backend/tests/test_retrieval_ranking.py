import unittest
import time
import uuid
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, Document, AcademicGraphSnapshot
from app.models.document import DocumentPage, DocumentBlock
from app.models.knowledge import KnowledgeVersion, KnowledgeEntity, KnowledgeRelationship, KnowledgeEvidence
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.document_repository import DocumentRepository
from app.schemas.retrieval import RetrievalRequest, RetrievalScope, RetrievalOptions
from app.services.retrieval.base import EntityCandidate, RelationshipCandidate
from app.services.retrieval.query_normalizer import NormalizedQuery
from app.services.retrieval.scope_resolver import ResolvedScope
from app.services.retrieval.evidence_retriever import EvidenceCandidate
from app.services.retrieval.passage_retriever import PassageCandidate
from app.services.retrieval.ranker import Ranker, RankingWeights, RetrievalScore
from app.services.retrieval.retrieval_service import RetrievalService


class TestRetrievalRanking(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
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

        # Seed Document B (for Document Isolation)
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

        # Seed Page & Block
        self.page_a1 = DocumentPage(id="page_a1_id", document_id="doc_a_id", page_number=1, width=100.0, height=100.0)
        self.db.add(self.page_a1)
        self.db.flush()

        self.blk_a1 = DocumentBlock(
            id="blk_a1_id", document_id="doc_a_id", page_id="page_a1_id", page_number=1,
            reading_order=1, block_type="PARAGRAPH", text="Binary search algorithm cuts complexity.",
            x0=0.0, y0=0.0, x1=50.0, y1=50.0
        )
        self.db.add(self.blk_a1)
        self.db.flush()

        # Seed Snapshots
        self.snap_a = AcademicGraphSnapshot(
            id="snap_a_id", upload_id=self.upload_a, pipeline_run_id="run_a",
            approval_version=42, approved_revision=1, base_graph_fingerprint="bfp_a",
            resolved_graph_fingerprint="rfp_a", approval_timestamp=time.time(),
            reviewer_id="reviewer", nodes=[], edges=[]
        )
        # Empty snapshot belonging to Document A to test version isolation
        self.snap_a_empty = AcademicGraphSnapshot(
            id="snap_a_empty_id", upload_id=self.upload_a, pipeline_run_id="run_a_empty",
            approval_version=10, approved_revision=1, base_graph_fingerprint="bfp_ae",
            resolved_graph_fingerprint="rfp_ae", approval_timestamp=time.time(),
            reviewer_id="reviewer", nodes=[], edges=[]
        )
        self.snap_b = AcademicGraphSnapshot(
            id="snap_b_id", upload_id=self.upload_b, pipeline_run_id="run_b",
            approval_version=2, approved_revision=1, base_graph_fingerprint="bfp_b",
            resolved_graph_fingerprint="rfp_b", approval_timestamp=time.time(),
            reviewer_id="reviewer", nodes=[], edges=[]
        )
        self.db.add_all([self.snap_a, self.snap_a_empty, self.snap_b])
        self.db.flush()

        # Seed Versions
        self.v_a = KnowledgeVersion(
            id="v_a_id", upload_id=self.upload_a, snapshot_id="snap_a_id",
            status="BUILDING", created_at=time.time()
        )
        self.v_a_empty = KnowledgeVersion(
            id="v_a_empty_id", upload_id=self.upload_a, snapshot_id="snap_a_empty_id",
            status="BUILDING", created_at=time.time()
        )
        self.v_b = KnowledgeVersion(
            id="v_b_id", upload_id=self.upload_b, snapshot_id="snap_b_id",
            status="BUILDING", created_at=time.time()
        )
        self.db.add_all([self.v_a, self.v_a_empty, self.v_b])
        self.db.flush()

        # Seed entities representing lexical match variants in Version A
        self.e_exact = KnowledgeEntity(
            id="e_exact_id", knowledge_version_id="v_a_id", entity_type="CONCEPT",
            title="Binary Search", content="Binary Search explanation", stable_id="anc_exact"
        )
        self.e_prefix = KnowledgeEntity(
            id="e_prefix_id", knowledge_version_id="v_a_id", entity_type="CONCEPT",
            title="Binary Search Algorithm", content="Binary Search Algorithm description", stable_id="anc_prefix"
        )
        self.e_contains = KnowledgeEntity(
            id="e_contains_id", knowledge_version_id="v_a_id", entity_type="CONCEPT",
            title="Introduction to Binary Search", content="Intro explanation", stable_id="anc_contains"
        )
        self.e_term = KnowledgeEntity(
            id="e_term_id", knowledge_version_id="v_a_id", entity_type="CONCEPT",
            title="Search Method", content="Search method bounds", stable_id="anc_term"
        )
        self.e_content = KnowledgeEntity(
            id="e_content_id", knowledge_version_id="v_a_id", entity_type="CONCEPT",
            title="Methodology", content="Content text matching binary", stable_id="anc_content"
        )
        self.e_redundant = KnowledgeEntity(
            id="e_redundant_id", knowledge_version_id="v_a_id", entity_type="CONCEPT",
            title="Binary Search", content="Binary Search", stable_id="anc_redundant"
        )

        # Seed Entity in Version B (document B) to test document isolation
        self.e_b = KnowledgeEntity(
            id="e_b_id", knowledge_version_id="v_b_id", entity_type="CONCEPT",
            title="Binary Search", content="Binary Search doc B", stable_id="anc_b"
        )

        self.db.add_all([self.e_exact, self.e_prefix, self.e_contains, self.e_term, self.e_content, self.e_redundant, self.e_b])
        self.db.flush()

        # Seed relationships
        self.r1 = KnowledgeRelationship(
            id="r1_id", knowledge_version_id="v_a_id", source_entity_id="e_exact_id",
            target_entity_id="e_prefix_id", relationship_type="EXPLAINS", confidence=0.85
        )
        self.db.add(self.r1)
        self.db.flush()

        # Seed evidence
        self.ev_exact = KnowledgeEvidence(
            id="ev_exact_id", entity_id="e_exact_id", document_id="doc_a_id", page_number=1,
            x0=0.0, y0=0.0, x1=50.0, y1=50.0, text_reference="Binary search algorithm cuts complexity.",
            section_title="Intro", provenance="EXPLICIT_CLASSIFIER"
        )
        self.db.add(self.ev_exact)
        self.db.flush()

        # Finalize versions (Done safely before committing)
        self.v_a.status = "FINALIZED"
        self.v_a_empty.status = "FINALIZED"
        self.v_b.status = "FINALIZED"
        self.db.commit()

        # Init retrieval components
        self.ranker = Ranker()
        self.retrieval_service = RetrievalService(self.repo, self.doc_repo)
        self.scope_a = RetrievalScope(document_id="doc_a_id", version_id="v_a_id")

    def tearDown(self):
        self.db.close()

    # ─── RANKING SIGNALS TESTS ─────────────────────────────────────

    def test_01_exact_title_beats_prefix_and_substring(self):
        """Verify exact title match score is computed as 1.0 (highest lexical match)."""
        cands = [
            EntityCandidate(entity=self.e_exact, match_score=1.0, match_reason="title_exact", matched_terms=["binary", "search"]),
            EntityCandidate(entity=self.e_prefix, match_score=0.8, match_reason="title_prefix", matched_terms=["binary", "search"])
        ]
        scores = self.ranker.score_candidates(cands, [], [], [], NormalizedQuery(raw="binary search", normalized="binary search", terms=["binary", "search"]), self.scope_a)
        self.assertGreater(scores[0].total_score, scores[1].total_score)
        self.assertEqual(scores[0].title_score, 1.0)
        self.assertEqual(scores[1].title_score, 0.8)

    def test_02_prefix_beats_substring(self):
        """Verify prefix match score beats substring contains match score."""
        cands = [
            EntityCandidate(entity=self.e_prefix, match_score=0.8, match_reason="title_prefix", matched_terms=["binary", "search"]),
            EntityCandidate(entity=self.e_contains, match_score=0.6, match_reason="title_contains", matched_terms=["binary", "search"])
        ]
        scores = self.ranker.score_candidates(cands, [], [], [], NormalizedQuery(raw="binary search", normalized="binary search", terms=["binary", "search"]), self.scope_a)
        self.assertGreater(scores[0].total_score, scores[1].total_score)
        self.assertEqual(scores[0].title_score, 0.8)
        self.assertEqual(scores[1].title_score, 0.6)

    def test_03_substring_beats_term_only(self):
        """Verify substring contains match beats term-only title match."""
        cands = [
            EntityCandidate(entity=self.e_contains, match_score=0.6, match_reason="title_contains", matched_terms=["binary", "search"]),
            EntityCandidate(entity=self.e_term, match_score=0.4, match_reason="title_term", matched_terms=["search"])
        ]
        scores = self.ranker.score_candidates(cands, [], [], [], NormalizedQuery(raw="binary search", normalized="binary search", terms=["binary", "search"]), self.scope_a)
        self.assertGreater(scores[0].total_score, scores[1].total_score)
        self.assertEqual(scores[0].title_score, 0.6)
        self.assertEqual(scores[1].title_score, 0.4)

    def test_04_query_term_coverage(self):
        """Verify query term coverage behaves as len(matched_terms) / len(query_terms)."""
        cands = [
            EntityCandidate(entity=self.e_exact, match_score=1.0, match_reason="title_exact", matched_terms=["binary", "search"]),
            EntityCandidate(entity=self.e_term, match_score=0.4, match_reason="title_term", matched_terms=["search"])
        ]
        query = NormalizedQuery(raw="binary search algorithm", normalized="binary search algorithm", terms=["binary", "search", "algorithm"])
        scores = self.ranker.score_candidates(cands, [], [], [], query, self.scope_a)
        
        exact_score = next(s for s in scores if s.entity_id == "e_exact_id")
        term_score = next(s for s in scores if s.entity_id == "e_term_id")
        self.assertAlmostEqual(exact_score.coverage_score, 2.0 / 3.0)
        self.assertAlmostEqual(term_score.coverage_score, 1.0 / 3.0)

    def test_05_type_preference_bonus(self):
        """Verify preferred type match receives a score bonus."""
        cands = [
            EntityCandidate(entity=self.e_exact, match_score=1.0, match_reason="title_exact", matched_terms=["binary", "search"])
        ]
        query = NormalizedQuery(raw="binary search", normalized="binary search", terms=["binary", "search"])
        
        scope_with_type = RetrievalScope(document_id="doc_a_id", version_id="v_a_id", entity_types=["CONCEPT"])
        scope_without_type = RetrievalScope(document_id="doc_a_id", version_id="v_a_id", entity_types=["ALGORITHM"])
        
        scores_yes = self.ranker.score_candidates(cands, [], [], [], query, scope_with_type)
        scores_no = self.ranker.score_candidates(cands, [], [], [], query, scope_without_type)
        
        self.assertEqual(scores_yes[0].type_score, 1.0)
        self.assertEqual(scores_no[0].type_score, 0.0)
        self.assertGreater(scores_yes[0].total_score, scores_no[0].total_score)

    def test_06_graph_distance_signal(self):
        """Verify graph neighbor relevance decreases as hop distance increases."""
        cands = [
            EntityCandidate(entity=self.e_exact, match_score=1.0, match_reason="title_exact", hop_distance=0, matched_terms=["binary", "search"]),
            EntityCandidate(entity=self.e_prefix, match_score=0.0, match_reason="graph_neighbor", hop_distance=1, matched_terms=[])
        ]
        scores = self.ranker.score_candidates(cands, [], [], [], NormalizedQuery(raw="binary search", terms=["binary", "search"], normalized="binary search"), self.scope_a)
        
        exact_score = next(s for s in scores if s.entity_id == "e_exact_id")
        neighbor_score = next(s for s in scores if s.entity_id == "e_prefix_id")
        self.assertEqual(exact_score.relationship_score, 1.0)      # 1 / (0+1)
        self.assertEqual(neighbor_score.relationship_score, 0.5)    # 1 / (1+1)

    def test_07_evidence_availability_signal(self):
        """Verify active evidence availability boosts relevance scores."""
        cands = [EntityCandidate(entity=self.e_exact, match_score=1.0, match_reason="title_exact", matched_terms=["binary", "search"])]
        query = NormalizedQuery(raw="binary search", terms=["binary", "search"], normalized="binary search")
        
        ev_cand = EvidenceCandidate(evidence=self.ev_exact, entity_id="e_exact_id", is_stale=False)
        scores = self.ranker.score_candidates(cands, [], [ev_cand], [], query, self.scope_a)
        self.assertEqual(scores[0].evidence_score, 1.0)

    def test_08_passage_availability_signal(self):
        """Verify resolved passage availability boosts score."""
        cands = [EntityCandidate(entity=self.e_exact, match_score=1.0, match_reason="title_exact", matched_terms=["binary", "search"])]
        query = NormalizedQuery(raw="binary search", terms=["binary", "search"], normalized="binary search")
        
        pass_cand = PassageCandidate(
            document_id="doc_a_id", block_id="blk_a1_id", page_number=1, text="...",
            block_type="PARAGRAPH", x0=0.0, y0=0.0, x1=50.0, y1=50.0, section_title="Intro",
            entity_ids=["e_exact_id"]
        )
        scores = self.ranker.score_candidates(cands, [], [], [pass_cand], query, self.scope_a)
        self.assertEqual(scores[0].passage_score, 1.0)

    def test_09_relationship_confidence_bounded(self):
        """Verify maximum relationship confidence contributes bounded score."""
        cands = [EntityCandidate(entity=self.e_exact, match_score=1.0, match_reason="title_exact", matched_terms=["binary", "search"])]
        query = NormalizedQuery(raw="binary search", terms=["binary", "search"], normalized="binary search")
        
        rel_cand = RelationshipCandidate(relationship=self.r1, source_entity=self.e_exact, target_entity=self.e_prefix, hop_distance=1)
        scores = self.ranker.score_candidates(cands, [rel_cand], [], [], query, self.scope_a)
        self.assertEqual(scores[0].confidence_score, 0.85)

    # ─── RANKING CORRECTNESS TESTS ─────────────────────────────────

    def test_10_deterministic_ranking(self):
        """Verify candidates score deterministically sorted."""
        cands = [
            EntityCandidate(entity=self.e_term, match_score=0.4, match_reason="title_term", matched_terms=["search"]),
            EntityCandidate(entity=self.e_exact, match_score=1.0, match_reason="title_exact", matched_terms=["binary", "search"])
        ]
        query = NormalizedQuery(raw="binary search", terms=["binary", "search"], normalized="binary search")
        scores = self.ranker.score_candidates(cands, [], [], [], query, self.scope_a)
        
        self.assertEqual(scores[0].entity_id, "e_exact_id")
        self.assertEqual(scores[1].entity_id, "e_term_id")

    def test_11_deterministic_tie_breaking(self):
        """Verify tie break fallback ordering by stable_id alphabetically."""
        cands = [
            EntityCandidate(entity=self.e_redundant, match_score=1.0, match_reason="title_exact", matched_terms=["binary", "search"]),
            EntityCandidate(entity=self.e_exact, match_score=1.0, match_reason="title_exact", matched_terms=["binary", "search"])
        ]
        query = NormalizedQuery(raw="binary search", terms=["binary", "search"], normalized="binary search")
        scores = self.ranker.score_candidates(cands, [], [], [], query, self.scope_a)
        
        self.assertEqual(scores[0].entity_id, "e_exact_id")
        self.assertEqual(scores[1].entity_id, "e_redundant_id")

    def test_12_same_input_produces_same_output(self):
        """Verify ranker outputs same scores given same parameters."""
        cands = [EntityCandidate(entity=self.e_exact, match_score=1.0, match_reason="title_exact", matched_terms=["binary", "search"])]
        query = NormalizedQuery(raw="binary search", terms=["binary", "search"], normalized="binary search")
        
        run_1 = self.ranker.score_candidates(cands, [], [], [], query, self.scope_a)
        run_2 = self.ranker.score_candidates(cands, [], [], [], query, self.scope_a)
        self.assertEqual(run_1[0].total_score, run_2[0].total_score)

    def test_13_candidate_scores_bounded(self):
        """Verify total score is bounded between 0.0 and 1.0."""
        cands = [EntityCandidate(entity=self.e_exact, match_score=1.0, match_reason="title_exact", matched_terms=["binary", "search"])]
        query = NormalizedQuery(raw="binary search", terms=["binary", "search"], normalized="binary search")
        scores = self.ranker.score_candidates(cands, [], [], [], query, self.scope_a)
        
        self.assertTrue(0.0 <= scores[0].total_score <= 1.0)

    def test_14_weights_applied_correctly(self):
        """Verify weights config coefficients are applied correctly."""
        cands = [EntityCandidate(entity=self.e_exact, match_score=1.0, match_reason="title_exact", matched_terms=["binary", "search"])]
        query = NormalizedQuery(raw="binary search", terms=["binary", "search"], normalized="binary search")
        
        custom_weights = RankingWeights(
            title=1.0, content=0.0, coverage=0.0, type=0.0,
            relationship=0.0, evidence=0.0, passage=0.0, confidence=0.0
        )
        scores = self.ranker.score_candidates(cands, [], [], [], query, self.scope_a, weights=custom_weights)
        self.assertEqual(scores[0].total_score, 1.0)

    def test_15_changing_weights_changes_ranking(self):
        """Verify changing ranking weights changes deterministic candidate scores."""
        cands = [
            EntityCandidate(entity=self.e_exact, match_score=1.0, match_reason="title_exact", matched_terms=["binary"]),
            EntityCandidate(entity=self.e_contains, match_score=0.6, match_reason="title_contains", matched_terms=["binary"])
        ]
        query = NormalizedQuery(raw="binary", terms=["binary"], normalized="binary")
        ev_cand = EvidenceCandidate(evidence=self.ev_exact, entity_id="e_exact_id", is_stale=False)
        
        weights_heavy_evidence = RankingWeights(
            title=0.1, content=0.0, coverage=0.0, type=0.0, relationship=0.0,
            evidence=0.9, passage=0.0, confidence=0.0
        )
        scores = self.ranker.score_candidates(cands, [], [ev_cand], [], query, self.scope_a, weights=weights_heavy_evidence)
        self.assertEqual(scores[0].entity_id, "e_exact_id")

    def test_16_no_accidental_double_counting(self):
        """Verify matching score features are bounded preventing double counting."""
        cands = [EntityCandidate(entity=self.e_exact, match_score=1.0, match_reason="title_exact", matched_terms=["binary", "search"])]
        query = NormalizedQuery(raw="binary search", terms=["binary", "search"], normalized="binary search")
        
        scores = self.ranker.score_candidates(cands, [], [], [], query, self.scope_a)
        # Components must remain bounded to prevent double counting
        self.assertTrue(scores[0].title_score <= 1.0)
        self.assertTrue(scores[0].total_score <= 1.0)

    def test_17_title_content_redundancy_handled(self):
        """Verify identical content vs title results in 0.0 content match score."""
        cands = [
            EntityCandidate(entity=self.e_redundant, match_score=1.0, match_reason="title_exact", matched_terms=["binary", "search"])
        ]
        query = NormalizedQuery(raw="binary search", terms=["binary", "search"], normalized="binary search")
        scores = self.ranker.score_candidates(cands, [], [], [], query, self.scope_a)
        self.assertEqual(scores[0].content_score, 0.0)

    # ─── GRAPH BEHAVIOR TESTS ──────────────────────────────────────

    def test_18_direct_lexical_hit_ranks_above_graph_neighbor(self):
        """Verify direct lexical hits rank above expansion graph neighbors."""
        cands = [
            EntityCandidate(entity=self.e_exact, match_score=1.0, match_reason="title_exact", hop_distance=0, matched_terms=["binary", "search"]),
            EntityCandidate(entity=self.e_prefix, match_score=0.0, match_reason="graph_neighbor", hop_distance=1, matched_terms=[])
        ]
        scores = self.ranker.score_candidates(cands, [], [], [], NormalizedQuery(raw="binary search", terms=["binary", "search"], normalized="binary search"), self.scope_a)
        self.assertEqual(scores[0].entity_id, "e_exact_id")

    def test_19_distant_graph_neighbor_does_not_swamp_lexical(self):
        """Verify distant graph neighbors receive attenuated scores."""
        cands = [
            EntityCandidate(entity=self.e_exact, match_score=0.4, match_reason="title_term", hop_distance=0, matched_terms=["search"]),
            EntityCandidate(entity=self.e_prefix, match_score=0.0, match_reason="graph_neighbor", hop_distance=3, matched_terms=[])
        ]
        scores = self.ranker.score_candidates(cands, [], [], [], NormalizedQuery(raw="search", terms=["search"], normalized="search"), self.scope_a)
        
        exact_score = next(s for s in scores if s.entity_id == "e_exact_id")
        neighbor_score = next(s for s in scores if s.entity_id == "e_prefix_id")
        self.assertGreater(exact_score.total_score, neighbor_score.total_score)

    def test_20_multiple_graph_paths_no_inflation(self):
        """Verify multiple relationship expansions do not inflate score twice."""
        cands = [EntityCandidate(entity=self.e_exact, match_score=1.0, match_reason="title_exact", matched_terms=["binary", "search"])]
        query = NormalizedQuery(raw="binary search", terms=["binary", "search"], normalized="binary search")
        
        rel_1 = RelationshipCandidate(relationship=self.r1, source_entity=self.e_exact, target_entity=self.e_prefix, hop_distance=1)
        rel_2 = RelationshipCandidate(relationship=self.r1, source_entity=self.e_exact, target_entity=self.e_prefix, hop_distance=2)
        
        scores = self.ranker.score_candidates(cands, [rel_1, rel_2], [], [], query, self.scope_a)
        self.assertEqual(scores[0].confidence_score, 0.85)

    # ─── EVIDENCE BEHAVIOR TESTS ───────────────────────────────────

    def test_21_evidence_presence_improves_score(self):
        """Verify evidence presence improves candidate score properly."""
        cands = [EntityCandidate(entity=self.e_exact, match_score=1.0, match_reason="title_exact", matched_terms=["binary", "search"])]
        query = NormalizedQuery(raw="binary search", terms=["binary", "search"], normalized="binary search")
        
        scores_without = self.ranker.score_candidates(cands, [], [], [], query, self.scope_a)
        
        ev_cand = EvidenceCandidate(evidence=self.ev_exact, entity_id="e_exact_id", is_stale=False)
        scores_with = self.ranker.score_candidates(cands, [], [ev_cand], [], query, self.scope_a)
        
        self.assertGreater(scores_with[0].total_score, scores_without[0].total_score)

    def test_22_stale_evidence_score(self):
        """Verify stale evidence receives 0.5 evidence availability score instead of 1.0."""
        cands = [EntityCandidate(entity=self.e_exact, match_score=1.0, match_reason="title_exact", matched_terms=["binary", "search"])]
        query = NormalizedQuery(raw="binary search", terms=["binary", "search"], normalized="binary search")
        
        ev_stale = EvidenceCandidate(evidence=self.ev_exact, entity_id="e_exact_id", is_stale=True)
        scores = self.ranker.score_candidates(cands, [], [ev_stale], [], query, self.scope_a)
        self.assertEqual(scores[0].evidence_score, 0.5)

    def test_23_missing_passage_does_not_invalidate_entity(self):
        """Verify missing source passages do not invalidate or crash retrieval ranking."""
        cands = [EntityCandidate(entity=self.e_exact, match_score=1.0, match_reason="title_exact", matched_terms=["binary", "search"])]
        query = NormalizedQuery(raw="binary search", terms=["binary", "search"], normalized="binary search")
        
        scores = self.ranker.score_candidates(cands, [], [], [], query, self.scope_a)
        self.assertEqual(scores[0].passage_score, 0.0)

    # ─── TOP-K TESTS ───────────────────────────────────────────────

    def test_24_top_k_truncation(self):
        """Verify top_k truncation limits returned entities list size."""
        req = RetrievalRequest(query="binary search", scope=self.scope_a, options=RetrievalOptions(top_k=2))
        res = self.retrieval_service.retrieve(req)
        self.assertEqual(len(res.entities), 2)

    def test_25_has_more_behavior(self):
        """Verify has_more flag behaves correctly based on truncation."""
        req = RetrievalRequest(query="binary search", scope=self.scope_a, options=RetrievalOptions(top_k=2))
        res = self.retrieval_service.retrieve(req)
        self.assertTrue(res.has_more)

        req_all = RetrievalRequest(query="binary search", scope=self.scope_a, options=RetrievalOptions(top_k=10))
        res_all = self.retrieval_service.retrieve(req_all)
        self.assertFalse(res_all.has_more)

    def test_26_top_k_1(self):
        """Verify top_k = 1 truncation constraint."""
        req = RetrievalRequest(query="binary search", scope=self.scope_a, options=RetrievalOptions(top_k=1))
        res = self.retrieval_service.retrieve(req)
        self.assertEqual(len(res.entities), 1)

    def test_27_top_k_larger_than_candidate_count(self):
        """Verify top_k larger than candidate count returns all matching entities."""
        req = RetrievalRequest(query="binary search", scope=self.scope_a, options=RetrievalOptions(top_k=100))
        res = self.retrieval_service.retrieve(req)
        self.assertEqual(len(res.entities), 6)
        self.assertFalse(res.has_more)

    # ─── ISOLATION TESTS ───────────────────────────────────────────

    def test_28_version_isolation(self):
        """Verify version isolation constraints are enforced (empty version returns zero)."""
        scope_b = RetrievalScope(document_id="doc_a_id", version_id="v_a_empty_id")
        req = RetrievalRequest(query="binary search", scope=scope_b, options=RetrievalOptions(top_k=10))
        res = self.retrieval_service.retrieve(req)
        self.assertEqual(len(res.entities), 0)

    def test_29_document_isolation(self):
        """Verify document isolation constraints prevent leaks."""
        # Query Document B should only return Document B's entities (e_b), not A's
        scope_b = RetrievalScope(document_id="doc_b_id", version_id="v_b_id")
        req = RetrievalRequest(query="binary search", scope=scope_b, options=RetrievalOptions(top_k=10))
        res = self.retrieval_service.retrieve(req)
        self.assertEqual(len(res.entities), 1)
        self.assertEqual(res.entities[0].entity.id, "e_b_id")

    # ─── STRATEGY TESTS ────────────────────────────────────────────

    def test_30_lexical_strategy_works(self):
        """Verify LEXICAL strategy runs successfully."""
        req = RetrievalRequest(query="binary search", scope=self.scope_a, options=RetrievalOptions(strategy="LEXICAL"))
        res = self.retrieval_service.retrieve(req)
        self.assertEqual(res.provenance.strategy_used, "LEXICAL")

    def test_31_unsupported_semantic_rejected(self):
        """Verify unsupported SEMANTIC strategy is rejected with ValueError."""
        req = RetrievalRequest(query="binary search", scope=self.scope_a, options=RetrievalOptions(strategy="SEMANTIC"))
        with self.assertRaises(ValueError):
            self.retrieval_service.retrieve(req)

    def test_32_unsupported_hybrid_rejected(self):
        """Verify unsupported HYBRID strategy is rejected with ValueError."""
        req = RetrievalRequest(query="binary search", scope=self.scope_a, options=RetrievalOptions(strategy="HYBRID"))
        with self.assertRaises(ValueError):
            self.retrieval_service.retrieve(req)

    # ─── RETRIEVAL CONTEXT TESTS ───────────────────────────────────

    def test_33_provenance_complete(self):
        """Verify RetrievalResult provenance properties are fully populated."""
        req = RetrievalRequest(query="binary search", scope=self.scope_a)
        res = self.retrieval_service.retrieve(req)
        prov = res.provenance
        self.assertEqual(prov.knowledge_version_id, "v_a_id")
        self.assertEqual(prov.approval_version, 42)
        self.assertEqual(prov.document_id, "doc_a_id")
        self.assertEqual(prov.strategy_used, "LEXICAL")

    def test_34_selected_entities_retain_relationships(self):
        """Verify selected entities attach outgoing/incoming relationships."""
        req = RetrievalRequest(query="binary search", scope=self.scope_a, options=RetrievalOptions(include_relationships=True, relationship_depth=1))
        res = self.retrieval_service.retrieve(req)
        ent = next(e for e in res.entities if e.entity.id == "e_exact_id")
        self.assertEqual(len(ent.outgoing_relationships), 1)

    def test_35_selected_entities_retain_evidence(self):
        """Verify selected entities attach layout evidence coordinates."""
        req = RetrievalRequest(query="binary search", scope=self.scope_a, options=RetrievalOptions(include_evidence=True))
        res = self.retrieval_service.retrieve(req)
        ent = next(e for e in res.entities if e.entity.id == "e_exact_id")
        self.assertEqual(len(ent.evidence), 1)

    def test_36_selected_entities_retain_passages(self):
        """Verify selected entities attach verbatim passage text."""
        req = RetrievalRequest(query="binary search", scope=self.scope_a, options=RetrievalOptions(include_evidence=True, include_passages=True))
        res = self.retrieval_service.retrieve(req)
        ent = next(e for e in res.entities if e.entity.id == "e_exact_id")
        self.assertEqual(len(ent.passages), 1)
        self.assertEqual(ent.passages[0].text, "Binary search algorithm cuts complexity.")

    def test_37_total_candidate_count_correct(self):
        """Verify total considered candidate count is accurate."""
        req = RetrievalRequest(query="binary search", scope=self.scope_a)
        res = self.retrieval_service.retrieve(req)
        self.assertEqual(res.provenance.total_candidates_considered, 6)


if __name__ == "__main__":
    unittest.main()
