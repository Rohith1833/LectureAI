import unittest
from typing import List
from pydantic import BaseModel

from app.schemas.document import BlockType
from app.services.intelligence import (
    BaseIntelligenceModule,
    ModuleMetadata,
    IntelligenceContext,
    AnnotationStore,
    BaseAnnotation,
    SemanticAnnotation,
    LayoutAnnotation,
    ConfidenceScore,
    DependencyResolver,
    CircularDependencyError,
    IntelligenceConfig,
    IntelligenceEngine,
    PipelineEventListener,
    PipelineEvent,
    PipelineStarted,
    ModuleStarted,
    ModuleFinished,
    ModuleFailed,
    PipelineFinished,
)


class DummyModule(BaseIntelligenceModule):
    """Simple concrete implementation of BaseIntelligenceModule for testing."""

    def __init__(self, name: str, deps: List[str] = None):
        self._metadata = ModuleMetadata(
            name=name,
            version="1.0.0",
            author="Test",
            stage="test_stage",
            dependencies=deps or [],
            enabled=True,
        )
        self.initialized = False
        self.cleaned_up = False

    @property
    def metadata(self) -> ModuleMetadata:
        return self._metadata

    def initialize(self, config: dict) -> None:
        self.initialized = True

    def execute(self, context: IntelligenceContext) -> None:
        # Add a test annotation
        anno = SemanticAnnotation(
            annotation_id=f"anno_{self.metadata.name}",
            target_id="block_1",
            provenance=self.metadata.name,
            confidence=ConfidenceScore(score=0.9),
            assigned_type=BlockType.HEADING,
        )
        context.annotation_store.add(anno)

    def cleanup(self) -> None:
        self.cleaned_up = True


class FailingModule(DummyModule):
    """Test module that raises an exception during execution."""

    def execute(self, context: IntelligenceContext) -> None:
        raise RuntimeError("Something failed inside module execution.")


class TestEventListener(PipelineEventListener):
    """Mock listener capturing events published during pipeline runs."""

    def __init__(self):
        self.events: List[PipelineEvent] = []

    def on_event(self, event: PipelineEvent) -> None:
        self.events.append(event)


class TestIntelligenceFramework(unittest.TestCase):

    def test_dependency_resolver_topological_sort(self):
        """Verify correct topological sorting of modules and missing/circular handling."""
        m_c = DummyModule("C", deps=[])
        m_b = DummyModule("B", deps=["C"])
        m_a = DummyModule("A", deps=["B"])

        # Topological Sort Resolution
        resolved = DependencyResolver.resolve([m_a, m_b, m_c])
        self.assertEqual(len(resolved), 3)
        self.assertEqual(resolved[0].metadata.name, "C")
        self.assertEqual(resolved[1].metadata.name, "B")
        self.assertEqual(resolved[2].metadata.name, "A")

        # Missing Dependency Error
        m_invalid = DummyModule("D", deps=["MissingModule"])
        with self.assertRaises(ValueError):
            DependencyResolver.resolve([m_invalid])

        # Circular Dependency Loop Error
        m_loop1 = DummyModule("L1", deps=["L2"])
        m_loop2 = DummyModule("L2", deps=["L1"])
        with self.assertRaises(CircularDependencyError):
            DependencyResolver.resolve([m_loop1, m_loop2])

    def test_annotation_store_operations(self):
        """Verify query, filter, update, remove, and statistical aggregation inside AnnotationStore."""
        store = AnnotationStore()

        semantic = SemanticAnnotation(
            annotation_id="a1",
            target_id="b100",
            provenance="module_1",
            confidence=ConfidenceScore(score=0.85),
            assigned_type=BlockType.PARAGRAPH,
        )
        layout = LayoutAnnotation(
            annotation_id="a2",
            target_id="b100",
            provenance="module_2",
            confidence=ConfidenceScore(score=1.0),
            x0=0.0,
            y0=0.0,
            x1=100.0,
            y1=100.0,
        )

        # Addition and Queries
        store.add(semantic)
        store.add(layout)
        
        self.assertEqual(len(store.find_by_target("b100")), 2)
        self.assertEqual(len(store.find_by_type(SemanticAnnotation)), 1)
        self.assertEqual(len(store.find_by_type(LayoutAnnotation)), 1)
        self.assertEqual(store.find("a1").confidence.score, 0.85)

        # Statistics
        stats = store.statistics()
        self.assertEqual(stats["total_count"], 2)
        self.assertEqual(stats["type_counts"]["SemanticAnnotation"], 1)
        self.assertEqual(stats["type_counts"]["LayoutAnnotation"], 1)

        # Update
        updated_semantic = semantic.model_copy()
        updated_semantic.confidence.score = 0.95
        store.update(updated_semantic)
        self.assertEqual(store.find("a1").confidence.score, 0.95)

        # Query filter lambda
        matches = store.query(lambda x: x.confidence.score > 0.9)
        self.assertEqual(len(matches), 2)  # both are now > 0.9

        # Removal
        removed = store.remove("a1")
        self.assertIsNotNone(removed)
        self.assertIsNone(store.find("a1"))
        self.assertEqual(store.statistics()["total_count"], 1)

    def test_engine_execution_and_telemetry(self):
        """Verify IntelligenceEngine executes successfully, triggers lifecycle hooks, and publishes events."""
        config = IntelligenceConfig()
        engine = IntelligenceEngine(config)

        # Subscribe mock event listener
        listener = TestEventListener()
        engine.publisher.subscribe(listener)

        # Initialize mock components
        m_c = DummyModule("C", deps=[])
        m_b = DummyModule("B", deps=["C"])
        modules = [m_b, m_c]

        # Execute
        context, report = engine.execute(
            document=None,
            page_metadata={},
            document_metadata=None,
            modules=modules,
            upload_id="test_upload_123",
        )

        # Check Report & Context
        self.assertTrue(report.success)
        self.assertEqual(report.execution_order, ["C", "B"])
        self.assertEqual(len(context.annotation_store.query(lambda x: True)), 2)
        self.assertEqual(report.overall_confidence_average, 0.9)

        # Check Lifecycle Hook Triggers
        self.assertTrue(m_c.initialized)
        self.assertTrue(m_c.cleaned_up)
        self.assertTrue(m_b.initialized)
        self.assertTrue(m_b.cleaned_up)

        # Check Event Subscriptions
        event_types = [type(e) for e in listener.events]
        self.assertIn(PipelineStarted, event_types)
        self.assertIn(ModuleStarted, event_types)
        self.assertIn(ModuleFinished, event_types)
        self.assertIn(PipelineFinished, event_types)

    def test_engine_error_isolation(self):
        """Verify module soft failures are isolated and do not crash the pipeline by default."""
        config = IntelligenceConfig()
        config.strict_mode = False

        engine = IntelligenceEngine(config)
        listener = TestEventListener()
        engine.publisher.subscribe(listener)

        m_ok = DummyModule("OKModule", deps=[])
        m_fail = FailingModule("FailingModule", deps=[])

        # Execute
        context, report = engine.execute(
            document=None,
            page_metadata={},
            document_metadata=None,
            modules=[m_ok, m_fail],
            upload_id="test_upload_err",
        )

        # Check Report shows soft failure was captured as warning but pipeline succeeded E2E
        self.assertTrue(report.success)
        self.assertFalse(report.metrics["FailingModule"].success)
        self.assertTrue(report.metrics["OKModule"].success)
        self.assertEqual(len(report.metrics["FailingModule"].warnings), 1)

        # Confirm failed events were published
        event_types = [type(e) for e in listener.events]
        self.assertIn(ModuleFailed, event_types)

    def test_engine_skipped_and_strict_modes(self):
        """Verify strict mode causes termination, and skipped modules are reported correctly."""
        from app.services.intelligence import ModuleConfig

        # 1. Test Skipped Module Registration
        config = IntelligenceConfig()
        config.modules["SkippedModule"] = ModuleConfig(enabled=False)

        engine = IntelligenceEngine(config)
        m_ok = DummyModule("OKModule", deps=[])
        m_skip = DummyModule("SkippedModule", deps=[])

        context, report = engine.execute(
            document=None,
            page_metadata={},
            document_metadata=None,
            modules=[m_ok, m_skip],
            upload_id="test_upload_skip",
        )

        self.assertTrue(report.success)
        self.assertIn("SkippedModule", report.metrics)
        self.assertTrue(report.metrics["SkippedModule"].skipped)
        self.assertTrue(report.metrics["SkippedModule"].success)
        self.assertFalse(report.metrics["OKModule"].skipped)

        # 2. Test Strict Mode Termination
        config_strict = IntelligenceConfig()
        config_strict.strict_mode = True

        engine_strict = IntelligenceEngine(config_strict)
        m_fail = FailingModule("FailingModule", deps=[])

        # Under strict mode, the engine execution handles the error and aborts E2E success
        ctx_st, rep_st = engine_strict.execute(
            document=None,
            page_metadata={},
            document_metadata=None,
            modules=[m_fail],
            upload_id="test_upload_strict",
        )
        self.assertFalse(rep_st.success)
        self.assertFalse(rep_st.metrics["FailingModule"].success)


if __name__ == "__main__":
    unittest.main()
