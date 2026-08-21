import unittest
import time
from app.schemas.academic import AcademicNode, AcademicEdge, AcademicNodeCategory
from app.schemas.review import ReconciliationStatus, ResolvedGraphResult, NodeReviewState
from app.models.review import AcademicOverride
from app.services.intelligence.review.overlay import AcademicOverlayService, calculate_graph_fingerprint


class TestReviewOverlay(unittest.TestCase):

    def setUp(self):
        # Build a base AcademicGraph representing:
        # Chapter 1 (an_ch1) -> contains Section 1.1 (an_sec1)
        # Section 1.1 contains Definition (an_def) and Example (an_ex)
        self.base_nodes = [
            AcademicNode(
                node_id="an_ch1",
                category=AcademicNodeCategory.CHAPTER,
                title="Chapter 1: Computation",
                anchor_key="anc_ch1",
                review_state=NodeReviewState.UNREVIEWED
            ),
            AcademicNode(
                node_id="an_sec1",
                category=AcademicNodeCategory.SECTION,
                title="Section 1.1: Turing Machines",
                anchor_key="anc_sec1",
                review_state=NodeReviewState.UNREVIEWED
            ),
            AcademicNode(
                node_id="an_def",
                category=AcademicNodeCategory.DEFINITION,
                title="Definition: Turing Machine",
                anchor_key="anc_def",
                review_state=NodeReviewState.UNREVIEWED
            ),
            AcademicNode(
                node_id="an_ex",
                category=AcademicNodeCategory.EXAMPLE,
                title="Example: Turing Machine run",
                anchor_key="anc_ex",
                review_state=NodeReviewState.UNREVIEWED
            )
        ]

        self.base_edges = [
            AcademicEdge(source_node_id="an_ch1", target_node_id="an_sec1", edge_type="CONTAINS"),
            AcademicEdge(source_node_id="an_sec1", target_node_id="an_def", edge_type="CONTAINS"),
            AcademicEdge(source_node_id="an_sec1", target_node_id="an_ex", edge_type="CONTAINS")
        ]

        self.service = AcademicOverlayService()

    def test_basic_compilation_no_overrides(self):
        """Verify overlay compiler works cleanly when no overrides exist."""
        result = self.service.compile_resolved_graph(self.base_nodes, self.base_edges, [])
        self.assertEqual(result.reconciliation_status, ReconciliationStatus.CLEAN)
        self.assertEqual(len(result.nodes), 4)
        self.assertEqual(len(result.edges), 3)
        self.assertEqual(result.base_graph_fingerprint, result.resolved_graph_fingerprint)

    def test_override_change_category(self):
        """Test CHANGE_CATEGORY mutation overlay."""
        override = AcademicOverride(
            id="ov_1",
            upload_id="upload_1",
            target_anchor_key="anc_ex",
            action_type="CHANGE_CATEGORY",
            payload={"new_category": "THEOREM"},
            is_active=True,
            created_at=time.time()
        )

        result = self.service.compile_resolved_graph(self.base_nodes, self.base_edges, [override])
        self.assertEqual(result.reconciliation_status, ReconciliationStatus.CLEAN)
        
        # Verify node properties updated in resolved graph
        ex_node = next(n for n in result.nodes if n.node_id == "an_ex")
        self.assertEqual(ex_node.category, AcademicNodeCategory.THEOREM)
        self.assertEqual(ex_node.review_state, NodeReviewState.MODIFIED)
        self.assertEqual(ex_node.metadata["original_category"], "EXAMPLE")
        self.assertIn("ov_1", ex_node.metadata["override_ids"])

        # Verify fingerprints differ
        self.assertNotEqual(result.base_graph_fingerprint, result.resolved_graph_fingerprint)

    def test_override_rename_title(self):
        """Test RENAME_TITLE mutation overlay."""
        override = AcademicOverride(
            id="ov_2",
            upload_id="upload_1",
            target_anchor_key="anc_def",
            action_type="RENAME_TITLE",
            payload={"new_title": "Turing Machine Definition"},
            is_active=True,
            created_at=time.time()
        )

        result = self.service.compile_resolved_graph(self.base_nodes, self.base_edges, [override])
        self.assertEqual(result.reconciliation_status, ReconciliationStatus.CLEAN)

        def_node = next(n for n in result.nodes if n.node_id == "an_def")
        self.assertEqual(def_node.title, "Turing Machine Definition")
        self.assertEqual(def_node.review_state, NodeReviewState.MODIFIED)
        self.assertEqual(def_node.metadata["original_title"], "Definition: Turing Machine")

    def test_override_reparent_node_and_cycle_check(self):
        """Test REPARENT_NODE with validation checks for cycle prevention."""
        # Reparent Example directly under Chapter 1
        override = AcademicOverride(
            id="ov_3",
            upload_id="upload_1",
            target_anchor_key="anc_ex",
            action_type="REPARENT_NODE",
            payload={"new_parent_id": "an_ch1"},
            is_active=True,
            created_at=time.time()
        )

        result = self.service.compile_resolved_graph(self.base_nodes, self.base_edges, [override])
        self.assertEqual(result.reconciliation_status, ReconciliationStatus.CLEAN)

        # Check edge updated
        ex_edge = next(e for e in result.edges if e.target_node_id == "an_ex" and e.edge_type == "CONTAINS")
        self.assertEqual(ex_edge.source_node_id, "an_ch1")

        # Force cycle: try to reparent Chapter 1 under Definition (which is a descendant)
        cycle_override = AcademicOverride(
            id="ov_cycle",
            upload_id="upload_1",
            target_anchor_key="anc_ch1",
            action_type="REPARENT_NODE",
            payload={"new_parent_id": "an_def"},
            is_active=True,
            created_at=time.time()
        )

        result_cycle = self.service.compile_resolved_graph(self.base_nodes, self.base_edges, [cycle_override])
        self.assertEqual(result_cycle.reconciliation_status, ReconciliationStatus.INVALID_GRAPH)
        self.assertTrue(len(result_cycle.validation_errors) > 0)
        self.assertIn("cycle", result_cycle.validation_errors[0])

    def test_override_create_node(self):
        """Test CREATE_NODE manual node overlay creation."""
        override = AcademicOverride(
            id="ov_create",
            upload_id="upload_1",
            target_anchor_key="manual_node_anchor",
            action_type="CREATE_NODE",
            payload={
                "category": "PROOF",
                "title": "Proof: Turing Machine Decidability",
                "target_block_id": "b_proof"
            },
            is_active=True,
            created_at=time.time()
        )

        result = self.service.compile_resolved_graph(self.base_nodes, self.base_edges, [override])
        self.assertEqual(result.reconciliation_status, ReconciliationStatus.CLEAN)
        
        # Verify node created
        manual_node = next((n for n in result.nodes if n.node_id == f"an_manual_{override.id}"), None)
        self.assertIsNotNone(manual_node)
        self.assertEqual(manual_node.category, AcademicNodeCategory.PROOF)
        self.assertEqual(manual_node.title, "Proof: Turing Machine Decidability")
        self.assertEqual(manual_node.target_block_id, "b_proof")

    def test_override_delete_node(self):
        """Test DELETE_NODE overlay updates review state to REJECTED and hides it from final graph."""
        override = AcademicOverride(
            id="ov_del",
            upload_id="upload_1",
            target_anchor_key="anc_ex",
            action_type="DELETE_NODE",
            payload={},
            is_active=True,
            created_at=time.time()
        )

        result = self.service.compile_resolved_graph(self.base_nodes, self.base_edges, [override])
        self.assertEqual(result.reconciliation_status, ReconciliationStatus.CLEAN)

        # Node should be hidden/filtered from resolved graph output
        ex_node = next((n for n in result.nodes if n.node_id == "an_ex"), None)
        self.assertIsNone(ex_node)

        # Edges connected to deleted node must be filtered out as well
        ex_edges = [e for e in result.edges if e.target_node_id == "an_ex" or e.source_node_id == "an_ex"]
        self.assertEqual(len(ex_edges), 0)

    def test_override_update_edge(self):
        """Test UPDATE_EDGE relationships overlay."""
        override = AcademicOverride(
            id="ov_edge",
            upload_id="upload_1",
            target_anchor_key="anc_def",
            action_type="UPDATE_EDGE",
            payload={
                "source_node_id": "an_def",
                "target_node_id": "an_ex",
                "edge_type": "EXPLAINS",
                "confidence": 0.95
            },
            is_active=True,
            created_at=time.time()
        )

        result = self.service.compile_resolved_graph(self.base_nodes, self.base_edges, [override])
        self.assertEqual(result.reconciliation_status, ReconciliationStatus.CLEAN)

        added_edge = next(e for e in result.edges if e.source_node_id == "an_def" and e.target_node_id == "an_ex")
        self.assertEqual(added_edge.edge_type, "EXPLAINS")
        self.assertEqual(added_edge.confidence, 0.95)

    def test_stale_override_handling(self):
        """Test stale override detection when target anchor key cannot be resolved."""
        override = AcademicOverride(
            id="ov_stale",
            upload_id="upload_1",
            target_anchor_key="missing_anchor",
            action_type="CHANGE_CATEGORY",
            payload={"new_category": "THEOREM"},
            is_active=True,
            created_at=time.time()
        )

        result = self.service.compile_resolved_graph(self.base_nodes, self.base_edges, [override])
        self.assertEqual(result.reconciliation_status, ReconciliationStatus.STALE_OVERRIDES)
        self.assertIn(override.id, result.stale_override_ids)
        self.assertTrue(len(result.validation_warnings) > 0)
        self.assertIn("stale", result.validation_warnings[0])

    def test_conflicting_same_node_overrides(self):
        """Test incompatible overrides targeting the same node are marked conflicted."""
        override1 = AcademicOverride(
            id="ov_c1",
            upload_id="upload_1",
            target_anchor_key="anc_ex",
            action_type="CHANGE_CATEGORY",
            payload={"new_category": "THEOREM"},
            is_active=True,
            created_at=time.time()
        )
        override2 = AcademicOverride(
            id="ov_c2",
            upload_id="upload_1",
            target_anchor_key="anc_ex",
            action_type="CHANGE_CATEGORY",
            payload={"new_category": "DEFINITION"}, # Incompatible payload
            is_active=True,
            created_at=time.time() + 1
        )

        result = self.service.compile_resolved_graph(self.base_nodes, self.base_edges, [override1, override2])
        self.assertEqual(result.reconciliation_status, ReconciliationStatus.CONFLICTS)
        self.assertIn("ov_c1", result.conflicted_override_ids)
        self.assertIn("ov_c2", result.conflicted_override_ids)

        # Category should remain unchanged (still EXAMPLE)
        ex_node = next(n for n in result.nodes if n.node_id == "an_ex")
        self.assertEqual(ex_node.category, AcademicNodeCategory.EXAMPLE)

    def test_input_immutability(self):
        """Prove that the compilation processes treats input graphs as read-only."""
        override = AcademicOverride(
            id="ov_mut",
            upload_id="upload_1",
            target_anchor_key="anc_ex",
            action_type="CHANGE_CATEGORY",
            payload={"new_category": "THEOREM"},
            is_active=True,
            created_at=time.time()
        )

        # Before compilation properties
        ex_category_before = self.base_nodes[3].category

        self.service.compile_resolved_graph(self.base_nodes, self.base_edges, [override])

        # After compilation properties should match exactly
        self.assertEqual(self.base_nodes[3].category, ex_category_before)

    def test_idempotency(self):
        """Verify overlay compilation is idempotent (running twice produces identical results)."""
        override1 = AcademicOverride(
            id="ov_i1",
            upload_id="upload_1",
            target_anchor_key="anc_def",
            action_type="RENAME_TITLE",
            payload={"new_title": "Turing Machine Definition"},
            is_active=True,
            created_at=time.time()
        )
        override2 = AcademicOverride(
            id="ov_i2",
            upload_id="upload_1",
            target_anchor_key="anc_ex",
            action_type="CHANGE_CATEGORY",
            payload={"new_category": "THEOREM"},
            is_active=True,
            created_at=time.time() + 1
        )

        result1 = self.service.compile_resolved_graph(self.base_nodes, self.base_edges, [override1, override2])
        result2 = self.service.compile_resolved_graph(self.base_nodes, self.base_edges, [override1, override2])

        self.assertEqual(result1.resolved_graph_fingerprint, result2.resolved_graph_fingerprint)
        self.assertEqual(
            [n.model_dump() for n in result1.nodes],
            [n.model_dump() for n in result2.nodes]
        )

    def test_reparent_node_retains_block_id(self):
        """Regression test: verify REPARENT_NODE modifies edge source ID but leaves target_block_id untouched."""
        override = AcademicOverride(
            id="ov_reparent_reg",
            upload_id="upload_1",
            target_anchor_key="anc_ex",
            action_type="REPARENT_NODE",
            payload={"new_parent_id": "an_ch1"},
            is_active=True,
            created_at=time.time()
        )

        ex_node_before = next(n for n in self.base_nodes if n.node_id == "an_ex")
        self.assertEqual(ex_node_before.target_block_id, None)  # Or whatever original block ID is

        result = self.service.compile_resolved_graph(self.base_nodes, self.base_edges, [override])
        
        # Verify node_id and target_block_id are exactly preserved
        ex_node_after = next(n for n in result.nodes if n.node_id == "an_ex")
        self.assertEqual(ex_node_after.node_id, "an_ex")
        self.assertEqual(ex_node_after.target_block_id, ex_node_before.target_block_id)

        # Verify edge containment updated
        contains_edge = next(e for e in result.edges if e.target_node_id == "an_ex" and e.edge_type == "CONTAINS")
        self.assertEqual(contains_edge.source_node_id, "an_ch1")

    def test_update_edge_with_anchor_resolution(self):
        """Verify UPDATE_EDGE works correctly using stable anchor keys instead of raw logical IDs."""
        override = AcademicOverride(
            id="ov_edge_anchors",
            upload_id="upload_1",
            target_anchor_key="anc_def",
            action_type="UPDATE_EDGE",
            payload={
                "source_anchor": "anc_def",
                "target_anchor": "anc_ex",
                "edge_type": "EXPLAINS",
                "confidence": 0.88
            },
            is_active=True,
            created_at=time.time()
        )

        result = self.service.compile_resolved_graph(self.base_nodes, self.base_edges, [override])
        self.assertEqual(result.reconciliation_status, ReconciliationStatus.CLEAN)

        resolved_edge = next(e for e in result.edges if e.edge_type == "EXPLAINS")
        self.assertEqual(resolved_edge.source_node_id, "an_def")
        self.assertEqual(resolved_edge.target_node_id, "an_ex")
        self.assertEqual(resolved_edge.confidence, 0.88)

    def test_create_node_stability_and_provenance(self):
        """Verify manually created node identity, anchor key safety, and stability across reruns."""
        override = AcademicOverride(
            id="ov_man_create",
            upload_id="upload_1",
            target_anchor_key="manual_anchor",
            action_type="CREATE_NODE",
            payload={
                "category": "THEOREM",
                "title": "Manual Theorem Node",
                "target_block_id": "b_manual_99",
                "anchor_key": "anc_manual_99"
            },
            is_active=True,
            created_at=time.time()
        )

        result1 = self.service.compile_resolved_graph(self.base_nodes, self.base_edges, [override])
        result2 = self.service.compile_resolved_graph(self.base_nodes, self.base_edges, [override])

        # Assert identity is identical across compiled runs
        node1 = next(n for n in result1.nodes if n.node_id == f"an_manual_{override.id}")
        node2 = next(n for n in result2.nodes if n.node_id == f"an_manual_{override.id}")
        self.assertEqual(node1.node_id, node2.node_id)
        self.assertEqual(node1.anchor_key, "anc_manual_99")
        self.assertEqual(node1.review_state, NodeReviewState.MODIFIED)
        self.assertEqual(node1.metadata["provenance"], "HUMAN_OVERRIDE")
        self.assertEqual(node1.target_block_id, "b_manual_99")


if __name__ == "__main__":
    unittest.main()

