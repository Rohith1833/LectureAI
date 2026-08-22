import os
import unittest
import time
import uuid
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.models import Base, Document, AcademicGraphSnapshot
from app.models.knowledge import KnowledgeVersion, KnowledgeEntity, KnowledgeRelationship
from app.repositories.knowledge_repository import KnowledgeRepository
from app.schemas.retrieval import RetrievalScope
from app.services.retrieval.base import EntityCandidate
from app.services.retrieval.query_normalizer import QueryNormalizer
from app.services.retrieval.scope_resolver import ScopeResolver, ResolvedScope
from app.services.retrieval.lexical_retriever import LexicalRetriever
from app.services.retrieval.graph_expander import GraphExpander, GraphExpansionResult


class TestRetrievalGraph(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.db_path = "test_retrieval_graph.db"
        cls.engine = create_engine(
            f"sqlite:///{cls.db_path}",
            connect_args={"check_same_thread": False}
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
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.TestingSessionLocal()
        self.repo = KnowledgeRepository(self.db)
        self.normalizer = QueryNormalizer()
        self.resolver = ScopeResolver(self.repo)
        self.retriever = LexicalRetriever(self.repo)
        self.expander = GraphExpander(self.repo)

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

        # Seed Document B (for isolation tests)
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

        # Seed snapshots
        self.snap_a = AcademicGraphSnapshot(
            id="snap_a_id",
            upload_id=self.upload_a,
            pipeline_run_id="run_a",
            approval_version=1,
            approved_revision=1,
            base_graph_fingerprint="bfp_a",
            resolved_graph_fingerprint="rfp_a",
            approval_timestamp=time.time(),
            reviewer_id="reviewer",
            nodes=[], edges=[]
        )
        self.snap_b = AcademicGraphSnapshot(
            id="snap_b_id",
            upload_id=self.upload_b,
            pipeline_run_id="run_b",
            approval_version=1,
            approved_revision=1,
            base_graph_fingerprint="bfp_b",
            resolved_graph_fingerprint="rfp_b",
            approval_timestamp=time.time(),
            reviewer_id="reviewer",
            nodes=[], edges=[]
        )
        self.db.add_all([self.snap_a, self.snap_b])
        self.db.flush()

        # Seed versions (BUILDING first)
        self.v_a = KnowledgeVersion(
            id="v_a_id",
            upload_id=self.upload_a,
            snapshot_id="snap_a_id",
            status="BUILDING",
            created_at=time.time()
        )
        self.v_b = KnowledgeVersion(
            id="v_b_id",
            upload_id=self.upload_b,
            snapshot_id="snap_b_id",
            status="BUILDING",
            created_at=time.time()
        )
        self.db.add_all([self.v_a, self.v_b])
        self.db.flush()

        # ─── SEED ENTITIES FOR VERSION A ───
        # e_search: "Binary Search", CONCEPT
        self.e_search = KnowledgeEntity(
            id="e_search_id",
            knowledge_version_id="v_a_id",
            entity_type="CONCEPT",
            title="Binary Search",
            content="Binary Search algorithm explanation",
            stable_id="anc_binary_search"
        )
        # e_algo: "Complexity Analysis", ALGORITHM
        self.e_algo = KnowledgeEntity(
            id="e_algo_id",
            knowledge_version_id="v_a_id",
            entity_type="ALGORITHM",
            title="Complexity Analysis",
            content="General algorithmic analysis concepts",
            stable_id="anc_complexity_analysis"
        )
        # e_sort: "Sorting Basics", CONCEPT
        self.e_sort = KnowledgeEntity(
            id="e_sort_id",
            knowledge_version_id="v_a_id",
            entity_type="CONCEPT",
            title="Sorting Basics",
            content="Introduction to sorting concepts",
            stable_id="anc_sorting_basics"
        )
        # e_bubble: "Bubble Sort", ALGORITHM
        self.e_bubble = KnowledgeEntity(
            id="e_bubble_id",
            knowledge_version_id="v_a_id",
            entity_type="ALGORITHM",
            title="Bubble Sort",
            content="Simple sorting algorithm details",
            stable_id="anc_bubble_sort"
        )
        # e_concept: "Big O notation", DEFINITION
        self.e_concept = KnowledgeEntity(
            id="e_concept_id",
            knowledge_version_id="v_a_id",
            entity_type="DEFINITION",
            title="Big O notation",
            content="Complexity bounds",
            stable_id="anc_big_o"
        )
        self.db.add_all([self.e_search, self.e_algo, self.e_sort, self.e_bubble, self.e_concept])
        self.db.flush()

        # ─── SEED ENTITIES FOR VERSION B (ISOLATION) ───
        self.e_b_search = KnowledgeEntity(
            id="e_b_search_id",
            knowledge_version_id="v_b_id",
            entity_type="CONCEPT",
            title="Binary Search",
            content="Isolated binary search in Document B",
            stable_id="anc_binary_search"
        )
        self.db.add(self.e_b_search)
        self.db.flush()

        # ─── SEED RELATIONSHIPS FOR VERSION A ───
        # 1. e_search -> e_algo (CONTAINS)
        self.r1 = KnowledgeRelationship(
            id="r1_id",
            knowledge_version_id="v_a_id",
            source_entity_id="e_search_id",
            target_entity_id="e_algo_id",
            relationship_type="CONTAINS",
            confidence=0.9
        )
        # 2. e_algo -> e_concept (PREREQUISITE_OF)
        self.r2 = KnowledgeRelationship(
            id="r2_id",
            knowledge_version_id="v_a_id",
            source_entity_id="e_algo_id",
            target_entity_id="e_concept_id",
            relationship_type="PREREQUISITE_OF",
            confidence=0.85
        )
        # 3. e_sort -> e_bubble (CONTAINS)
        self.r3 = KnowledgeRelationship(
            id="r3_id",
            knowledge_version_id="v_a_id",
            source_entity_id="e_sort_id",
            target_entity_id="e_bubble_id",
            relationship_type="CONTAINS",
            confidence=0.95
        )
        # 4. e_bubble -> e_concept (PREREQUISITE_OF)
        self.r4 = KnowledgeRelationship(
            id="r4_id",
            knowledge_version_id="v_a_id",
            source_entity_id="e_bubble_id",
            target_entity_id="e_concept_id",
            relationship_type="PREREQUISITE_OF",
            confidence=0.75
        )
        # 5. Cycle: e_search -> e_sort (EXPLAINS)
        self.r5 = KnowledgeRelationship(
            id="r5_id",
            knowledge_version_id="v_a_id",
            source_entity_id="e_search_id",
            target_entity_id="e_sort_id",
            relationship_type="EXPLAINS",
            confidence=0.8
        )
        # 6. Cycle: e_sort -> e_search (ILLUSTRATES)
        self.r6 = KnowledgeRelationship(
            id="r6_id",
            knowledge_version_id="v_a_id",
            source_entity_id="e_sort_id",
            target_entity_id="e_search_id",
            relationship_type="ILLUSTRATES",
            confidence=0.8
        )
        # 7. Duplicate Path: e_search -> e_concept (EXPLAINS) (1 hop vs 2 hops via e_algo)
        self.r7 = KnowledgeRelationship(
            id="r7_id",
            knowledge_version_id="v_a_id",
            source_entity_id="e_search_id",
            target_entity_id="e_concept_id",
            relationship_type="EXPLAINS",
            confidence=0.9
        )
        self.db.add_all([self.r1, self.r2, self.r3, self.r4, self.r5, self.r6, self.r7])
        self.db.flush()

        # Finalize versions A and B
        self.v_a.status = "FINALIZED"
        self.v_b.status = "FINALIZED"
        self.db.commit()

        # Build resolved scopes
        self.scope_a = ResolvedScope(document_id="doc_a_id", version_id="v_a_id")
        self.scope_b = ResolvedScope(document_id="doc_b_id", version_id="v_b_id")

    def tearDown(self):
        self.db.close()

    # ─── LEXICAL RETRIEVAL TESTS ──────────────────────────────────

    def test_01_lexical_exact_title_match(self):
        """Verify exact title match yields score 1.0 and title_exact reason."""
        nq = self.normalizer.normalize("Binary Search")
        res = self.retriever.retrieve_candidates(nq, self.scope_a, RetrievalScope(document_id="doc_a_id"))
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].entity.id, "e_search_id")
        self.assertEqual(res[0].match_score, 1.0)
        self.assertEqual(res[0].match_reason, "title_exact")

    def test_02_lexical_title_prefix_match(self):
        """Verify title prefix match yields score 0.8 and title_prefix reason."""
        nq = self.normalizer.normalize("binary")
        res = self.retriever.retrieve_candidates(nq, self.scope_a, RetrievalScope(document_id="doc_a_id"))
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].entity.id, "e_search_id")
        self.assertEqual(res[0].match_score, 0.8)
        self.assertEqual(res[0].match_reason, "title_prefix")

    def test_03_lexical_title_substring_match(self):
        """Verify title substring match yields score 0.6 and title_contains reason."""
        nq = self.normalizer.normalize("basics")
        res = self.retriever.retrieve_candidates(nq, self.scope_a, RetrievalScope(document_id="doc_a_id"))
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].entity.id, "e_sort_id")
        self.assertEqual(res[0].match_score, 0.6)
        self.assertEqual(res[0].match_reason, "title_contains")

    def test_04_lexical_title_term_match(self):
        """Verify standard term-based matching on title yields score 0.4 and title_term reason."""
        nq = self.normalizer.normalize("basics bubble")
        res = self.retriever.retrieve_candidates(nq, self.scope_a, RetrievalScope(document_id="doc_a_id"))
        self.assertEqual(len(res), 2)
        entity_ids = [c.entity.id for c in res]
        self.assertIn("e_sort_id", entity_ids)
        self.assertIn("e_bubble_id", entity_ids)
        reasons = [c.match_reason for c in res]
        self.assertTrue(any(r in ["title_term", "title_contains", "title_prefix"] for r in reasons))

    def test_05_lexical_content_match(self):
        """Verify content matching yields score 0.2 and content_contains reason."""
        nq = self.normalizer.normalize("explanation")
        res = self.retriever.retrieve_candidates(nq, self.scope_a, RetrievalScope(document_id="doc_a_id"))
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].entity.id, "e_search_id")
        self.assertEqual(res[0].match_score, 0.2)
        self.assertEqual(res[0].match_reason, "content_contains")

    def test_06_lexical_multi_term_query(self):
        """Verify multi-term query maps matches across all terms."""
        nq = self.normalizer.normalize("basics bubble")
        res = self.retriever.retrieve_candidates(nq, self.scope_a, RetrievalScope(document_id="doc_a_id"))
        self.assertEqual(len(res), 2)
        entity_ids = [c.entity.id for c in res]
        self.assertIn("e_sort_id", entity_ids)
        self.assertIn("e_bubble_id", entity_ids)

    def test_07_lexical_entity_type_filtering(self):
        """Verify candidate list is restricted to the specified entity types filter."""
        nq = self.normalizer.normalize("bubble")
        filters = RetrievalScope(document_id="doc_a_id", entity_types=["ALGORITHM"])
        res = self.retriever.retrieve_candidates(nq, self.scope_a, filters)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].entity.id, "e_bubble_id")
        self.assertEqual(res[0].entity.entity_type, "ALGORITHM")

    def test_08_lexical_no_results(self):
        """Verify query with no terms in version returns empty candidate list."""
        nq = self.normalizer.normalize("quantum mechanics")
        res = self.retriever.retrieve_candidates(nq, self.scope_a, RetrievalScope(document_id="doc_a_id"))
        self.assertEqual(len(res), 0)

    # ─── GRAPH EXPANSION TESTS ────────────────────────────────────

    def test_09_graph_depth_0(self):
        """Verify depth 0 returns only direct lexical hits with no relationships."""
        nq = self.normalizer.normalize("Binary Search")
        hits = self.retriever.retrieve_candidates(nq, self.scope_a, RetrievalScope(document_id="doc_a_id"))
        expanded = self.expander.expand(hits, self.scope_a, RetrievalScope(document_id="doc_a_id"), max_depth=0)
        
        self.assertEqual(len(expanded.entities), 1)
        self.assertEqual(expanded.entities[0].entity.id, "e_search_id")
        self.assertEqual(expanded.entities[0].hop_distance, 0)
        self.assertEqual(len(expanded.relationships), 0)

    def test_10_graph_depth_1(self):
        """Verify depth 1 retrieves neighbors directly connected to lexical hits."""
        nq = self.normalizer.normalize("Binary Search")
        hits = self.retriever.retrieve_candidates(nq, self.scope_a, RetrievalScope(document_id="doc_a_id"))
        expanded = self.expander.expand(hits, self.scope_a, RetrievalScope(document_id="doc_a_id"), max_depth=1)
        
        entity_ids = [c.entity.id for c in expanded.entities]
        self.assertEqual(len(entity_ids), 4)  # 1 hit + 3 neighbors (e_algo, e_sort, e_concept)
        self.assertIn("e_search_id", entity_ids)
        self.assertIn("e_algo_id", entity_ids)
        self.assertIn("e_sort_id", entity_ids)
        self.assertIn("e_concept_id", entity_ids)
        
        h_map = {c.entity.id: c.hop_distance for c in expanded.entities}
        self.assertEqual(h_map["e_search_id"], 0)
        self.assertEqual(h_map["e_algo_id"], 1)
        self.assertEqual(h_map["e_sort_id"], 1)
        self.assertEqual(h_map["e_concept_id"], 1)

        # 4 relationships traversed (r1, r5, r6, r7)
        self.assertEqual(len(expanded.relationships), 4)

    def test_11_graph_depth_2(self):
        """Verify depth 2 traverses 2 hops from hit entities."""
        nq = self.normalizer.normalize("Binary Search")
        hits = self.retriever.retrieve_candidates(nq, self.scope_a, RetrievalScope(document_id="doc_a_id"))
        expanded = self.expander.expand(hits, self.scope_a, RetrievalScope(document_id="doc_a_id"), max_depth=2)
        
        entity_ids = [c.entity.id for c in expanded.entities]
        self.assertEqual(len(entity_ids), 5)  # All 5 nodes reached
        h_map = {c.entity.id: c.hop_distance for c in expanded.entities}
        self.assertEqual(h_map["e_bubble_id"], 2)
        self.assertEqual(h_map["e_concept_id"], 1)  # Minimum hop distance kept

    def test_12_graph_depth_3(self):
        """Verify depth 3 handles three hops correctly."""
        nq = self.normalizer.normalize("Binary Search")
        hits = self.retriever.retrieve_candidates(nq, self.scope_a, RetrievalScope(document_id="doc_a_id"))
        expanded = self.expander.expand(hits, self.scope_a, RetrievalScope(document_id="doc_a_id"), max_depth=3)
        self.assertEqual(len(expanded.entities), 5)

    def test_13_graph_relationship_type_filtering(self):
        """Verify graph expansion is restricted to specified relationship types."""
        nq = self.normalizer.normalize("Binary Search")
        hits = self.retriever.retrieve_candidates(nq, self.scope_a, RetrievalScope(document_id="doc_a_id"))
        filters = RetrievalScope(document_id="doc_a_id", relationship_types=["CONTAINS"])
        expanded = self.expander.expand(hits, self.scope_a, filters, max_depth=1)
        
        entity_ids = [c.entity.id for c in expanded.entities]
        self.assertEqual(len(entity_ids), 2)  # e_search (0) + e_algo (1)
        self.assertIn("e_search_id", entity_ids)
        self.assertIn("e_algo_id", entity_ids)
        self.assertEqual(len(expanded.relationships), 1)

    def test_14_graph_cycle_handling(self):
        """Verify that cyclical relationships do not cause infinite loops."""
        nq = self.normalizer.normalize("Binary Search")
        hits = self.retriever.retrieve_candidates(nq, self.scope_a, RetrievalScope(document_id="doc_a_id"))
        expanded = self.expander.expand(hits, self.scope_a, RetrievalScope(document_id="doc_a_id"), max_depth=3)
        self.assertTrue(len(expanded.entities) > 0)

    def test_15_graph_duplicate_path_min_hop_distance(self):
        """Verify that reaching an entity via multiple paths preserves the minimum hop distance."""
        nq = self.normalizer.normalize("Binary Search")
        hits = self.retriever.retrieve_candidates(nq, self.scope_a, RetrievalScope(document_id="doc_a_id"))
        expanded = self.expander.expand(hits, self.scope_a, RetrievalScope(document_id="doc_a_id"), max_depth=2)
        
        h_map = {c.entity.id: c.hop_distance for c in expanded.entities}
        self.assertEqual(h_map["e_concept_id"], 1)

    def test_16_graph_deterministic_ordering(self):
        """Verify candidate list sorting is deterministic."""
        nq = self.normalizer.normalize("basics bubble")
        hits = self.retriever.retrieve_candidates(nq, self.scope_a, RetrievalScope(document_id="doc_a_id"))
        expanded = self.expander.expand(hits, self.scope_a, RetrievalScope(document_id="doc_a_id"), max_depth=1)
        
        # e_bubble matches "bubble" (prefix of Bubble Sort, score 0.8)
        # e_sort matches "basics" (substring of Sorting Basics, score 0.6)
        # So Bubble Sort (e_bubble) must be first, then Sorting Basics (e_sort)
        self.assertEqual(expanded.entities[0].entity.id, "e_bubble_id")
        self.assertEqual(expanded.entities[1].entity.id, "e_sort_id")

    # ─── ISOLATION TESTS ──────────────────────────────────────────

    def test_17_version_isolation(self):
        """Verify search scoped to Version A never returns candidates from Version B."""
        nq = self.normalizer.normalize("Binary Search")
        hits = self.retriever.retrieve_candidates(nq, self.scope_a, RetrievalScope(document_id="doc_a_id"))
        for cand in hits:
            self.assertEqual(cand.entity.knowledge_version_id, "v_a_id")
            self.assertNotEqual(cand.entity.id, "e_b_search_id")

    def test_18_document_isolation(self):
        """Verify search scoped to Document B never returns candidates from Document A."""
        nq = self.normalizer.normalize("Binary Search")
        hits = self.retriever.retrieve_candidates(nq, self.scope_b, RetrievalScope(document_id="doc_b_id"))
        for cand in hits:
            self.assertEqual(cand.entity.knowledge_version_id, "v_b_id")
            self.assertEqual(cand.entity.id, "e_b_search_id")
            self.assertNotEqual(cand.entity.id, "e_search_id")

    # ─── CORRECTNESS EDGE CASES ───────────────────────────────────

    def test_19_graph_empty_graph(self):
        """Verify expansion on version with no entities or relationships returns empty lists."""
        # Create doc D with no entities at all
        upload_d = str(uuid.uuid4())
        doc_d = Document(
            id="doc_d_id",
            upload_id=upload_d,
            status="processed",
            extraction_timestamp="2026-08-21T12:00:00Z",
            processing_time=1.0,
            review_state="APPROVED"
        )
        self.db.add(doc_d)
        self.db.flush()

        snap_d = AcademicGraphSnapshot(
            id="snap_d_id",
            upload_id=upload_d,
            pipeline_run_id="run_d",
            approval_version=1,
            approved_revision=1,
            base_graph_fingerprint="bfp_d",
            resolved_graph_fingerprint="rfp_d",
            approval_timestamp=time.time(),
            reviewer_id="reviewer",
            nodes=[], edges=[]
        )
        self.db.add(snap_d)
        self.db.flush()

        v_d = KnowledgeVersion(
            id="v_d_id",
            upload_id=upload_d,
            snapshot_id="snap_d_id",
            status="BUILDING",
            created_at=time.time()
        )
        self.db.add(v_d)
        self.db.flush()

        v_d.status = "FINALIZED"
        self.db.commit()
        
        scope_d = ResolvedScope(document_id="doc_d_id", version_id="v_d_id")
        nq = self.normalizer.normalize("Binary Search")
        hits = self.retriever.retrieve_candidates(nq, scope_d, RetrievalScope(document_id="doc_d_id"))
        expanded = self.expander.expand(hits, scope_d, RetrievalScope(document_id="doc_d_id"), max_depth=1)
        self.assertEqual(len(expanded.entities), 0)
        self.assertEqual(len(expanded.relationships), 0)

    def test_20_graph_dangling_relationship_neighbor_skips(self):
        """Verify that relationships pointing to non-existent neighbor entity IDs are skipped safely."""
        # Mock get_entity to return None for neighbor_id "e_concept_id" (Complexity Theory / Big O notation)
        # e_algo_id links to e_concept_id via r2
        original_get_entity = self.repo.get_entity

        def mock_get_entity(version_id, entity_id):
            if entity_id == "e_concept_id":
                return None
            return original_get_entity(version_id, entity_id)

        self.repo.get_entity = mock_get_entity

        nq = self.normalizer.normalize("Binary Search")
        hits = self.retriever.retrieve_candidates(nq, self.scope_a, RetrievalScope(document_id="doc_a_id"))
        expanded = self.expander.expand(hits, self.scope_a, RetrievalScope(document_id="doc_a_id"), max_depth=2)
        
        # Concept entity (Complexity Theory) is skipped safely and does not exist in expanded entities
        entity_ids = [c.entity.id for c in expanded.entities]
        self.assertNotIn("e_concept_id", entity_ids)

        # Restore original function
        self.repo.get_entity = original_get_entity


if __name__ == "__main__":
    unittest.main()
