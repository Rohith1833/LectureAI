import unittest
from typing import List, Dict, Any, Tuple

from app.schemas.document import (
    DocumentExtractionResult,
    DocumentMetadataSchema,
    PageSchema,
    BlockSchema,
    BlockType,
    BoundingBox,
)
from app.services.normalization.base import (
    BaseNormalizer,
    PipelineLifecycleHook,
    ImmutableMetadata,
    NormalizationContext,
    NormalizationReport,
    StageResult,
    StageMetrics,
    TransformationRecord,
)
from app.services.normalization.pipeline import NormalizationPipeline


class MockNormalizerA(BaseNormalizer):
    """Mock normalizer that appends a suffix to all paragraph texts."""

    def get_name(self) -> str:
        return "NORMALIZER_A"

    def run(
        self, doc: DocumentExtractionResult, context: NormalizationContext
    ) -> StageResult:
        updated_blocks = []
        transformations = []
        
        # Clone extraction blocks
        for b in doc.blocks:
            old_text = b.text
            new_text = f"{old_text} [A]"
            
            # Create transformation record (calculates hashes automatically)
            record = TransformationRecord.create_record(
                step_name=self.get_name(),
                target_block_id=b.block_id,
                action="modified",
                reason="Appended A suffix",
                original_text=old_text,
                transformed_text=new_text,
                verbose=context.debug_mode,
            )
            transformations.append(record)

            b_copy = b.model_copy()
            b_copy.text = new_text
            updated_blocks.append(b_copy)

        doc_copy = doc.model_copy()
        doc_copy.blocks = updated_blocks

        metrics = StageMetrics(
            execution_time_ms=0.0,
            modified_blocks_count=len(updated_blocks),
        )

        return StageResult(document=doc_copy, transformations=transformations, metrics=metrics)


class MockNormalizerB(BaseNormalizer):
    """Mock normalizer that appends a suffix to all paragraph texts."""

    def get_name(self) -> str:
        return "NORMALIZER_B"

    def run(
        self, doc: DocumentExtractionResult, context: NormalizationContext
    ) -> StageResult:
        updated_blocks = []
        transformations = []
        
        for b in doc.blocks:
            old_text = b.text
            new_text = f"{old_text} [B]"
            
            record = TransformationRecord.create_record(
                step_name=self.get_name(),
                target_block_id=b.block_id,
                action="modified",
                reason="Appended B suffix",
                original_text=old_text,
                transformed_text=new_text,
                verbose=context.debug_mode,
            )
            transformations.append(record)

            b_copy = b.model_copy()
            b_copy.text = new_text
            updated_blocks.append(b_copy)

        doc_copy = doc.model_copy()
        doc_copy.blocks = updated_blocks

        metrics = StageMetrics(
            execution_time_ms=0.0,
            modified_blocks_count=len(updated_blocks),
        )

        return StageResult(document=doc_copy, transformations=transformations, metrics=metrics)


class FailingNormalizer(BaseNormalizer):
    """Mock normalizer that raises a runtime exception."""

    def get_name(self) -> str:
        return "FAILING_NORMALIZER"

    def run(
        self, doc: DocumentExtractionResult, context: NormalizationContext
    ) -> StageResult:
        raise RuntimeError("Something went wrong inside Normalizer step run.")


class TestLifecycleHook(PipelineLifecycleHook):
    """Mock lifecycle observer to record callback executions."""

    def __init__(self):
        self.log = []

    def before_pipeline(self, pipeline, doc, context):
        self.log.append("before_pipeline")

    def before_stage(self, pipeline, stage_name, doc, context):
        self.log.append(f"before_{stage_name}")

    def after_stage(self, pipeline, stage_name, doc, context, stage_result):
        self.log.append(f"after_{stage_name}")

    def pipeline_complete(self, pipeline, doc, context, report):
        self.log.append("pipeline_complete")


class TestNormalizationArchitecture(unittest.TestCase):
    def setUp(self):
        # Create standard layout blocks mock input
        self.metadata = DocumentMetadataSchema(
            title="Test Doc", author="Tester", page_count=1, pdf_version="1.4"
        )
        self.blocks = [
            BlockSchema(
                block_id="block-101",
                page_number=1,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                text="Hello World",
                bounding_box=BoundingBox(x0=0, y0=0, x1=10, y1=10),
            )
        ]
        self.doc = DocumentExtractionResult(
            upload_id="test-upload-id",
            status="processed",
            metadata=self.metadata,
            pages=[PageSchema(page_number=1, width=100.0, height=100.0)],
            blocks=self.blocks,
            tables=[],
            images=[],
            extraction_timestamp="2026-08-04T00:00:00Z",
            processing_time=0.1,
        )

    def test_pipeline_ordered_execution_and_caching(self):
        """Verify that pipeline runs steps in correct order and saves document snapshots."""
        pipeline = NormalizationPipeline()
        pipeline.register_step(MockNormalizerA())
        pipeline.register_step(MockNormalizerB())

        meta = ImmutableMetadata(upload_id="u123", config={})
        context = NormalizationContext(meta, debug_mode=True)

        res_doc, report = pipeline.execute(self.doc, context)

        # Assert correct order of execution suffix chains: text -> text [A] -> text [A] [B]
        self.assertEqual(res_doc.blocks[0].text, "Hello World [A] [B]")
        self.assertEqual(report.steps_executed, ["NORMALIZER_A", "NORMALIZER_B"])
        self.assertEqual(report.total_transformations, 2)

        # Assert document snapshots versioning history is correct
        history = context.get_snapshots_history()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0][0], "NORMALIZER_A")
        self.assertEqual(history[1][0], "NORMALIZER_B")
        
        # Verify first snapshot block text
        snap_a = context.get_snapshot("NORMALIZER_A")
        self.assertIsNotNone(snap_a)
        self.assertEqual(snap_a["blocks"][0]["text"], "Hello World [A]")

    def test_configuration_loading(self):
        """Verify that steps can be individually enabled or disabled via configuration dictionary."""
        pipeline = NormalizationPipeline()
        pipeline.register_step(MockNormalizerA())
        pipeline.register_step(MockNormalizerB())

        # Disable NORMALIZER_A
        meta = ImmutableMetadata(
            upload_id="u123",
            config={"normalization_steps": {"NORMALIZER_A": False, "NORMALIZER_B": True}},
        )
        context = NormalizationContext(meta)

        res_doc, report = pipeline.execute(self.doc, context)

        # Assert NORMALIZER_A was skipped, and only NORMALIZER_B ran: text -> text [B]
        self.assertEqual(res_doc.blocks[0].text, "Hello World [B]")
        self.assertEqual(report.steps_executed, ["NORMALIZER_B"])

    def test_fault_tolerance(self):
        """Verify that when a stage fails with an exception, subsequent steps continue executing."""
        pipeline = NormalizationPipeline()
        pipeline.register_step(MockNormalizerA())
        pipeline.register_step(FailingNormalizer())
        pipeline.register_step(MockNormalizerB())

        meta = ImmutableMetadata(upload_id="u123", config={})
        context = NormalizationContext(meta)

        res_doc, report = pipeline.execute(self.doc, context)

        # Text should still be modified by B even though FAILING_NORMALIZER crashed: text -> text [A] [B]
        self.assertEqual(res_doc.blocks[0].text, "Hello World [A] [B]")
        self.assertEqual(report.steps_executed, ["NORMALIZER_A", "FAILING_NORMALIZER", "NORMALIZER_B"])

        # Check errors are registered in metrics map
        self.assertIn("FAILING_NORMALIZER", report.stage_metrics)
        metrics_fail = report.stage_metrics["FAILING_NORMALIZER"]
        self.assertEqual(len(metrics_fail.errors), 1)
        self.assertIn("Something went wrong", metrics_fail.errors[0])

    def test_lightweight_vs_verbose_history(self):
        """Verify that lightweight records avoid storing text while verbose captures full diffs."""
        pipeline = NormalizationPipeline()
        pipeline.register_step(MockNormalizerA())

        # Lightweight mode (default debug_mode = False)
        meta = ImmutableMetadata(upload_id="u123")
        context_light = NormalizationContext(meta, debug_mode=False)
        _, report_light = pipeline.execute(self.doc, context_light)
        
        record_light = report_light.transformations[0]
        self.assertIsNotNone(record_light.original_hash)
        self.assertIsNotNone(record_light.transformed_hash)
        self.assertIsNone(record_light.original_text)
        self.assertIsNone(record_light.transformed_text)

        # Verbose/Debug mode (debug_mode = True)
        context_verbose = NormalizationContext(meta, debug_mode=True)
        _, report_verbose = pipeline.execute(self.doc, context_verbose)
        
        record_verbose = report_verbose.transformations[0]
        self.assertEqual(record_verbose.original_text, "Hello World")
        self.assertEqual(record_verbose.transformed_text, "Hello World [A]")

    def test_lifecycle_hooks(self):
        """Verify lifecycle hook triggers execute in correct order."""
        pipeline = NormalizationPipeline()
        pipeline.register_step(MockNormalizerA())
        hook = TestLifecycleHook()
        pipeline.register_hook(hook)

        meta = ImmutableMetadata(upload_id="u123")
        context = NormalizationContext(meta)
        pipeline.execute(self.doc, context)

        expected_sequence = [
            "before_pipeline",
            "before_NORMALIZER_A",
            "after_NORMALIZER_A",
            "pipeline_complete",
        ]
        self.assertEqual(hook.log, expected_sequence)

    def test_unicode_normalizer_behavior(self):
        """Verify typographic character replacements and mappings in UnicodeNormalizer."""
        from app.services.normalization.unicode_normalizer import UnicodeNormalizer
        normalizer = UnicodeNormalizer()
        
        meta = ImmutableMetadata(upload_id="u123")
        context = NormalizationContext(meta, debug_mode=True)
        
        input_blocks = [
            BlockSchema(
                block_id="b1",
                page_number=1,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                text="ﬁrst ﬂight and the “smart quotes” – en-dash — em-dash … ellipsis",
                bounding_box=BoundingBox(x0=0, y0=0, x1=10, y1=10),
            )
        ]
        doc = self.doc.model_copy()
        doc.blocks = input_blocks
        
        result = normalizer.run(doc, context)
        expected = 'first flight and the "smart quotes" - en-dash - em-dash ... ellipsis'
        self.assertEqual(result.document.blocks[0].text, expected)
        self.assertEqual(result.metrics.modified_blocks_count, 1)
        self.assertEqual(len(result.transformations), 1)

    def test_control_character_normalizer_behavior(self):
        """Verify removal of control and formatting characters except safe spacing."""
        from app.services.normalization.control_character_normalizer import ControlCharacterNormalizer
        normalizer = ControlCharacterNormalizer()
        
        meta = ImmutableMetadata(upload_id="u123")
        context = NormalizationContext(meta, debug_mode=True)
        
        input_blocks = [
            BlockSchema(
                block_id="b1",
                page_number=1,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                text="Line1\nLine2\u200b\x00Text",
                bounding_box=BoundingBox(x0=0, y0=0, x1=10, y1=10),
            )
        ]
        doc = self.doc.model_copy()
        doc.blocks = input_blocks
        
        result = normalizer.run(doc, context)
        self.assertEqual(result.document.blocks[0].text, "Line1\nLine2Text")
        self.assertEqual(result.metrics.modified_blocks_count, 1)

    def test_whitespace_normalizer_behavior(self):
        """Verify tab replacements, space collapsing, line trimming, and blank line limits."""
        from app.services.normalization.whitespace_normalizer import WhitespaceNormalizer
        normalizer = WhitespaceNormalizer()
        
        meta = ImmutableMetadata(upload_id="u123")
        context = NormalizationContext(meta, debug_mode=True)
        
        input_blocks = [
            BlockSchema(
                block_id="b1",
                page_number=1,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                text="  TrimMe  \n\n\n\tTabbed   Spaces   \n\n\nLine",
                bounding_box=BoundingBox(x0=0, y0=0, x1=10, y1=10),
            )
        ]
        doc = self.doc.model_copy()
        doc.blocks = input_blocks
        
        result = normalizer.run(doc, context)
        expected = "TrimMe\n\nTabbed Spaces\n\nLine"
        self.assertEqual(result.document.blocks[0].text, expected)

    def test_empty_block_normalizer_behavior(self):
        """Verify empty and whitespace-only blocks are deleted from document."""
        from app.services.normalization.empty_block_normalizer import EmptyBlockNormalizer
        normalizer = EmptyBlockNormalizer()
        
        meta = ImmutableMetadata(upload_id="u123")
        context = NormalizationContext(meta, debug_mode=True)
        
        input_blocks = [
            BlockSchema(
                block_id="b1",
                page_number=1,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                text="Good text",
                bounding_box=BoundingBox(x0=0, y0=0, x1=10, y1=10),
            ),
            BlockSchema(
                block_id="b2",
                page_number=1,
                reading_order=2,
                block_type=BlockType.PARAGRAPH,
                text="   \n \t ",
                bounding_box=BoundingBox(x0=0, y0=0, x1=10, y1=10),
            ),
        ]
        doc = self.doc.model_copy()
        doc.blocks = input_blocks
        
        result = normalizer.run(doc, context)
        self.assertEqual(len(result.document.blocks), 1)
        self.assertEqual(result.document.blocks[0].block_id, "b1")
        self.assertEqual(result.metrics.removed_blocks_count, 1)

    def test_default_pipeline_execution_and_idempotency(self):
        """Test default pipeline executes all normalizers in order and is fully idempotent."""
        pipeline = NormalizationPipeline.create_default_pipeline()
        self.assertEqual(len(pipeline.steps), 4)
        
        input_blocks = [
            BlockSchema(
                block_id="b1",
                page_number=1,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                text="ﬁrst\tﬂight “smart”\n\n\n\u200bLine",
                bounding_box=BoundingBox(x0=0, y0=0, x1=10, y1=10),
            ),
            BlockSchema(
                block_id="b2",
                page_number=1,
                reading_order=2,
                block_type=BlockType.PARAGRAPH,
                text="  \u200b  ",
                bounding_box=BoundingBox(x0=0, y0=0, x1=10, y1=10),
            ),
        ]
        doc = self.doc.model_copy()
        doc.blocks = input_blocks
        
        meta = ImmutableMetadata(upload_id="u123")
        context1 = NormalizationContext(meta, debug_mode=True)
        
        # First Run
        res_doc1, report1 = pipeline.execute(doc, context1)
        
        # Assertions
        self.assertEqual(len(res_doc1.blocks), 1)
        expected = 'first flight "smart"\n\nLine'
        self.assertEqual(res_doc1.blocks[0].text, expected)
        
        # Second Run (Idempotency)
        context2 = NormalizationContext(meta, debug_mode=True)
        res_doc2, report2 = pipeline.execute(res_doc1, context2)
        
        self.assertEqual(res_doc2.blocks[0].text, expected)
        self.assertEqual(report2.total_transformations, 0)


if __name__ == "__main__":
    unittest.main()
