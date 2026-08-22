import unittest
from pydantic import ValidationError

from app.schemas.retrieval import (
    RetrievalScope,
    RetrievalOptions,
    RetrievalRequest,
    PassageSchema,
    RetrievedEntity,
    RetrievalProvenance,
    RetrievalResult
)
from app.services.retrieval.base import BaseRetriever


class TestRetrievalContracts(unittest.TestCase):

    def test_01_retrieval_scope_validation(self):
        """Verify RetrievalScope field requirements and validation constraints."""
        # 1. Success case: document_id provided
        scope_data = {
            "document_id": "doc_123",
            "version_id": "ver_456",
            "entity_types": ["CONCEPT", "DEFINITION"],
            "relationship_types": ["PREREQUISITE_OF"]
        }
        scope = RetrievalScope(**scope_data)
        self.assertEqual(scope.document_id, "doc_123")
        self.assertEqual(scope.version_id, "ver_456")
        self.assertEqual(scope.entity_types, ["CONCEPT", "DEFINITION"])
        self.assertEqual(scope.relationship_types, ["PREREQUISITE_OF"])

        # 2. Success case: optional fields omitted
        scope_minimal = RetrievalScope(document_id="doc_minimal")
        self.assertEqual(scope_minimal.document_id, "doc_minimal")
        self.assertIsNone(scope_minimal.version_id)
        self.assertIsNone(scope_minimal.entity_types)
        self.assertIsNone(scope_minimal.relationship_types)

        # 3. Failure case: missing required document_id
        with self.assertRaises(ValidationError):
            RetrievalScope()

    def test_02_retrieval_options_defaults_and_bounds(self):
        """Verify default values and numerical bounds on RetrievalOptions."""
        # 1. Check default values
        opts = RetrievalOptions()
        self.assertEqual(opts.top_k, 10)
        self.assertTrue(opts.include_relationships)
        self.assertTrue(opts.include_evidence)
        self.assertTrue(opts.include_passages)
        self.assertEqual(opts.relationship_depth, 1)
        self.assertEqual(opts.strategy, "LEXICAL")

        # 2. Check top_k boundary constraints (must be between 1 and 100)
        opts_valid_bound = RetrievalOptions(top_k=100, relationship_depth=3)
        self.assertEqual(opts_valid_bound.top_k, 100)
        self.assertEqual(opts_valid_bound.relationship_depth, 3)

        with self.assertRaises(ValidationError):
            RetrievalOptions(top_k=0)

        with self.assertRaises(ValidationError):
            RetrievalOptions(top_k=101)

        # 3. Check relationship_depth constraints (must be between 0 and 3)
        with self.assertRaises(ValidationError):
            RetrievalOptions(relationship_depth=-1)

        with self.assertRaises(ValidationError):
            RetrievalOptions(relationship_depth=4)

    def test_03_retrieval_request_nested_validation(self):
        """Verify RetrievalRequest parses nested scope, options, and validates query length."""
        # 1. Success case
        req_data = {
            "query": "quantum entanglement",
            "scope": {"document_id": "doc_1"},
            "options": {"top_k": 5}
        }
        req = RetrievalRequest(**req_data)
        self.assertEqual(req.query, "quantum entanglement")
        self.assertEqual(req.scope.document_id, "doc_1")
        self.assertEqual(req.options.top_k, 5)

        # 2. Check query minimum length (min_length=1)
        with self.assertRaises(ValidationError):
            RetrievalRequest(query="", scope={"document_id": "doc_1"})

        # 3. Check query maximum length (max_length=2048)
        long_query = "a" * 2049
        with self.assertRaises(ValidationError):
            RetrievalRequest(query=long_query, scope={"document_id": "doc_1"})

    def test_04_passage_schema_coordinates(self):
        """Verify PassageSchema parses coordinate bounds correctly."""
        passage_data = {
            "block_id": "blk_1",
            "page_number": 2,
            "text": "Verbatim document excerpt.",
            "block_type": "PARAGRAPH",
            "section_title": "Section 1",
            "x0": 10.5, "y0": 20.0, "x1": 100.5, "y1": 120.0
        }
        passage = PassageSchema(**passage_data)
        self.assertEqual(passage.block_id, "blk_1")
        self.assertEqual(passage.page_number, 2)
        self.assertEqual(passage.x0, 10.5)
        self.assertEqual(passage.y1, 120.0)

    def test_05_provenance_contract(self):
        """Verify RetrievalProvenance field mapping."""
        prov_data = {
            "knowledge_version_id": "ver_uuid",
            "approval_version": 2,
            "document_id": "doc_uuid",
            "strategy_used": "LEXICAL",
            "query_terms": ["quantum", "entanglement"],
            "total_candidates_considered": 15
        }
        prov = RetrievalProvenance(**prov_data)
        self.assertEqual(prov.knowledge_version_id, "ver_uuid")
        self.assertEqual(prov.approval_version, 2)
        self.assertEqual(prov.total_candidates_considered, 15)

    def test_06_retriever_interface_immutability(self):
        """Verify BaseRetriever abstract class cannot be directly instantiated."""
        with self.assertRaises(TypeError):
            BaseRetriever()


if __name__ == "__main__":
    unittest.main()
