import unittest
from app.schemas.review import NodeReviewState, DocumentReviewState
from app.schemas.academic import AcademicNodeCategory, AcademicNode
from app.services.intelligence.review.identity import (
    normalize_title,
    compute_text_hash,
    generate_anchor_key,
    resolve_anchor_keys_for_nodes,
)
from app.services.intelligence.graph import DocumentGraph, DocumentReadingGraphAnnotation
from app.schemas.document import DocumentExtractionResult, DocumentMetadataSchema, PageSchema, BlockSchema, BlockType, BoundingBox


class TestReviewIdentity(unittest.TestCase):

    def test_review_state_transitions(self):
        """Verify NodeReviewState and DocumentReviewState values and boundaries."""
        # Validate node review state constraints
        self.assertEqual(NodeReviewState.UNREVIEWED.value, "UNREVIEWED")
        self.assertEqual(NodeReviewState.ACCEPTED.value, "ACCEPTED")
        self.assertEqual(NodeReviewState.REJECTED.value, "REJECTED")
        self.assertEqual(NodeReviewState.MODIFIED.value, "MODIFIED")

        # Validate document review state constraints
        self.assertEqual(DocumentReviewState.NEEDS_REVIEW.value, "NEEDS_REVIEW")
        self.assertEqual(DocumentReviewState.APPROVED.value, "APPROVED")

    def test_normalize_title(self):
        """Ensure title normalization produces stable paths, stripping punctuation and casing."""
        self.assertEqual(normalize_title(None), "root")
        self.assertEqual(normalize_title(""), "root")
        self.assertEqual(normalize_title("Chapter 1: Principles of Computation!"), "chapter-1-principles-of-computation")
        self.assertEqual(normalize_title("  1.1 Turing   Machines--  "), "11-turing-machines")

    def test_compute_text_hash(self):
        """Ensure text hashes normalize whitespace and symbols."""
        self.assertEqual(compute_text_hash(None), "")
        self.assertEqual(compute_text_hash(""), "")
        
        text1 = "Definition 1.1: A Turing Machine is a model of computation."
        text2 = "  definition 11: a turing machine is a model of computation.  "
        self.assertEqual(compute_text_hash(text1), compute_text_hash(text2))

        different_text = "Definition 1.2: A Turing Machine differs."
        self.assertNotEqual(compute_text_hash(text1), compute_text_hash(different_text))

    def test_anchor_generation_determinism(self):
        """Verify anchor keys are stable under identical inputs but differ on structural changes."""
        upload_id = "upload_123"
        path = "chapter-1/section-11"
        type_str = "DEFINITION"
        text_hash = compute_text_hash("A Turing Machine is a model of computation.")
        
        # Test determinism
        anchor1 = generate_anchor_key(upload_id, path, type_str, text_hash, 0)
        anchor2 = generate_anchor_key(upload_id, path, type_str, text_hash, 0)
        self.assertEqual(anchor1, anchor2)

        # Test upload_id variance
        self.assertNotEqual(anchor1, generate_anchor_key("upload_456", path, type_str, text_hash, 0))

        # Test path variance
        self.assertNotEqual(anchor1, generate_anchor_key(upload_id, "chapter-2", type_str, text_hash, 0))

        # Test category variance
        self.assertNotEqual(anchor1, generate_anchor_key(upload_id, path, "THEOREM", text_hash, 0))

        # Test ordinal index variance
        self.assertNotEqual(anchor1, generate_anchor_key(upload_id, path, type_str, text_hash, 1))

    def test_resolve_anchor_keys_collision_detection(self):
        """Verify duplicate nodes under identical sections and text generate correct collision diagnostics."""
        pages = [PageSchema(page_number=1, width=600.0, height=800.0)]
        blocks = [
            BlockSchema(
                block_id="b_ch1",
                page_number=1,
                reading_order=0,
                block_type=BlockType.HEADING,
                text="Chapter 1: Computation",
                bounding_box=BoundingBox(x0=50.0, y0=50.0, x1=400.0, y1=85.0),
            ),
            # Identical node 1
            BlockSchema(
                block_id="b_def1",
                page_number=1,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                text="Definition: Turing Machine is a model.",
                parent_block_id="b_ch1",
                bounding_box=BoundingBox(x0=50.0, y0=100.0, x1=550.0, y1=120.0),
            ),
            # Identical node 2 (causes collision because it shares enclosing path, text hash, category and ordinal)
            BlockSchema(
                block_id="b_def2",
                page_number=1,
                reading_order=2,
                block_type=BlockType.PARAGRAPH,
                text="Definition: Turing Machine is a model.",
                parent_block_id="b_ch1",
                bounding_box=BoundingBox(x0=50.0, y0=130.0, x1=550.0, y1=150.0),
            ),
        ]

        doc = DocumentExtractionResult(
            upload_id="test_collision_upload",
            status="processed",
            metadata=DocumentMetadataSchema(page_count=1),
            pages=pages,
            blocks=blocks,
            tables=[],
            images=[],
            extraction_timestamp="t",
            processing_time=0.0,
        )

        graph_anno = DocumentReadingGraphAnnotation(
            annotation_id="temp_g",
            target_id="test_collision_upload",
            provenance="temp",
            confidence={"score": 1.0},
            nodes=["b_ch1", "b_def1", "b_def2"],
            edges=[]
        )

        doc_graph = DocumentGraph(doc, graph_anno)

        nodes_data = [
            ("b_def1", "Definition: Turing Machine is a model.", AcademicNodeCategory.DEFINITION),
            ("b_def2", "Definition: Turing Machine is a model.", AcademicNodeCategory.DEFINITION),
        ]

        # Call key resolver
        # Ordinal count resolves collisions by assigning distinct ordinals in sequence, but wait!
        # If we resolve them sequentially, they will receive ordinals 0 and 1, so the generated anchors will be distinct!
        # What if they have identical ordinals? They can only have identical ordinals if they are not processed in sequence,
        # or if they are mock-resolved with identical count configurations.
        # Let's verify ordinal assignment:
        anchor_map, diagnostics = resolve_anchor_keys_for_nodes("test_collision_upload", nodes_data, doc_graph)
        
        # Ordinals are distinct (0 and 1), so anchors are distinct and len(diagnostics) == 0
        self.assertEqual(len(diagnostics), 0)
        self.assertNotEqual(anchor_map["b_def1"], anchor_map["b_def2"])

        # To force a collision, we mock generate_anchor_key to return a constant hash
        from unittest.mock import patch
        with patch("app.services.intelligence.review.identity.generate_anchor_key", return_value="mocked_constant_hash"):
            anchor_map_coll, diagnostics_coll = resolve_anchor_keys_for_nodes("test_collision_upload", nodes_data, doc_graph)
            
        self.assertTrue(len(diagnostics_coll) > 0)
        self.assertEqual(diagnostics_coll[0]["anchor_key"], "mocked_constant_hash")
        self.assertEqual(len(diagnostics_coll[0]["conflicts"]), 2)


if __name__ == "__main__":
    unittest.main()
