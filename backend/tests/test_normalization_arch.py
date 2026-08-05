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
        """Test default pipeline executes all 7 normalizers in order and is fully idempotent."""
        pipeline = NormalizationPipeline.create_default_pipeline()
        self.assertEqual(len(pipeline.steps), 7)
        
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
        # b2 deleted, text normalized
        self.assertEqual(len(res_doc1.blocks), 1)
        expected = 'first flight "smart"\n\nLine'
        self.assertEqual(res_doc1.blocks[0].text, expected)
        
        # Second Run (Idempotency)
        context2 = NormalizationContext(meta, debug_mode=True)
        res_doc2, report2 = pipeline.execute(res_doc1, context2)
        
        self.assertEqual(res_doc2.blocks[0].text, expected)
        self.assertEqual(report2.total_transformations, 0)

    def test_paragraph_normalizer_behavior(self):
        """Verify ParagraphNormalizer merges broken paragraphs and soft line breaks."""
        from app.services.normalization.paragraph_normalizer import ParagraphNormalizer
        normalizer = ParagraphNormalizer()
        
        meta = ImmutableMetadata(upload_id="u123")
        context = NormalizationContext(meta, debug_mode=True)
        
        # Scenario: two paragraph blocks split by layout lines on same page
        # same font, sequential reading order, first ends lowercase continuation
        input_blocks = [
            BlockSchema(
                block_id="b1",
                page_number=1,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                font_family="Times",
                font_size=12.0,
                text="This book explains software\ntesting principles used",
                bounding_box=BoundingBox(x0=50.0, y0=100.0, x1=300.0, y1=120.0),
            ),
            BlockSchema(
                block_id="b2",
                page_number=1,
                reading_order=2,
                block_type=BlockType.PARAGRAPH,
                font_family="Times",
                font_size=12.0,
                text="in industry.",
                bounding_box=BoundingBox(x0=50.0, y0=125.0, x1=200.0, y1=140.0),
            ),
        ]
        doc = self.doc.model_copy()
        doc.blocks = input_blocks
        
        result = normalizer.run(doc, context)
        # Expected: single paragraph block with soft breaks cleaned:
        # "This book explains software testing principles used in industry."
        self.assertEqual(len(result.document.blocks), 1)
        expected_text = "This book explains software testing principles used in industry."
        self.assertEqual(result.document.blocks[0].text, expected_text)
        self.assertEqual(result.metrics.merged_blocks_count, 1)

    def test_cross_page_continuation(self):
        """Verify ParagraphNormalizer merges paragraph wrappers across page transitions."""
        from app.services.normalization.paragraph_normalizer import ParagraphNormalizer
        normalizer = ParagraphNormalizer()
        
        meta = ImmutableMetadata(upload_id="u123")
        context = NormalizationContext(meta, debug_mode=True)
        
        input_blocks = [
            BlockSchema(
                block_id="b1",
                page_number=1,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                font_family="Times",
                font_size=12.0,
                text="The objective of software",
                bounding_box=BoundingBox(x0=50.0, y0=800.0, x1=300.0, y1=820.0),
            ),
            BlockSchema(
                block_id="b2",
                page_number=2,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                font_family="Times",
                font_size=12.0,
                text="testing is to verify code correctness.",
                bounding_box=BoundingBox(x0=50.0, y0=50.0, x1=300.0, y1=70.0),
            ),
        ]
        doc = self.doc.model_copy()
        doc.blocks = input_blocks
        
        result = normalizer.run(doc, context)
        self.assertEqual(len(result.document.blocks), 1)
        expected_text = "The objective of software testing is to verify code correctness."
        self.assertEqual(result.document.blocks[0].text, expected_text)

    def test_hyphenation_normalizer_behavior(self):
        """Verify hyphenation repairs within-block and cross-block splits."""
        from app.services.normalization.hyphenation_normalizer import HyphenationNormalizer
        normalizer = HyphenationNormalizer()
        
        meta = ImmutableMetadata(upload_id="u123")
        context = NormalizationContext(meta, debug_mode=True)
        
        input_blocks = [
            # Within-block: "informa-\ntion" -> "information"
            BlockSchema(
                block_id="b1",
                page_number=1,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                text="We need to extract informa-\ntion from this.",
                bounding_box=BoundingBox(x0=50.0, y0=100.0, x1=300.0, y1=120.0),
            ),
            # Cross-block: ends with hyphen, next block starts with lowercase
            BlockSchema(
                block_id="b2",
                page_number=1,
                reading_order=2,
                block_type=BlockType.PARAGRAPH,
                font_family="Times",
                font_size=12.0,
                text="This is real-time processing and it is dec-",
                bounding_box=BoundingBox(x0=50.0, y0=140.0, x1=300.0, y1=160.0),
            ),
            BlockSchema(
                block_id="b3",
                page_number=1,
                reading_order=3,
                block_type=BlockType.PARAGRAPH,
                font_family="Times",
                font_size=12.0,
                text="larative layout.",
                bounding_box=BoundingBox(x0=50.0, y0=165.0, x1=200.0, y1=180.0),
            ),
        ]
        doc = self.doc.model_copy()
        doc.blocks = input_blocks
        
        result = normalizer.run(doc, context)
        # Expected: b1 within-block repaired, b2 and b3 cross-block merged.
        # Note: "real-time" on same line must stay untouched.
        self.assertEqual(len(result.document.blocks), 2)
        self.assertEqual(result.document.blocks[0].text, "We need to extract information from this.")
        self.assertEqual(result.document.blocks[1].text, "This is real-time processing and it is declarative layout.")
        self.assertEqual(result.metrics.removed_blocks_count, 1)

    def test_header_footer_normalizer_behavior(self):
        """Verify running header/footer and page number repetition and classification logic."""
        from app.services.normalization.header_footer_normalizer import HeaderFooterNormalizer
        normalizer = HeaderFooterNormalizer()
        
        # Test pages sizes
        pages = [
            PageSchema(page_number=1, width=600.0, height=800.0),
            PageSchema(page_number=2, width=600.0, height=800.0),
        ]
        
        # Setup blocks:
        # - "Chapter 1" (header candidate, but ONLY on page 1 -> Chapter heading protection check!)
        # - "LectureAI Book" (static header, appears at y1=50 on Page 1 and Page 2)
        # - "Page 1" and "Page 2" (page number candidate at bottom margin y0=760)
        input_blocks = [
            BlockSchema(
                block_id="b1",
                page_number=1,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                font_family="Times",
                font_size=10.0,
                text="Chapter 1 Introduction",
                bounding_box=BoundingBox(x0=50.0, y0=30.0, x1=200.0, y1=45.0), # top 20%
            ),
            BlockSchema(
                block_id="b2",
                page_number=1,
                reading_order=2,
                block_type=BlockType.PARAGRAPH,
                font_family="Times",
                font_size=10.0,
                text="LectureAI Book",
                bounding_box=BoundingBox(x0=400.0, y0=30.0, x1=550.0, y1=45.0), # top 20%
            ),
            BlockSchema(
                block_id="b3",
                page_number=1,
                reading_order=3,
                block_type=BlockType.PARAGRAPH,
                text="1",
                bounding_box=BoundingBox(x0=300.0, y0=770.0, x1=310.0, y1=785.0), # bottom 20%
            ),
            BlockSchema(
                block_id="b4",
                page_number=2,
                reading_order=1,
                block_type=BlockType.PARAGRAPH,
                font_family="Times",
                font_size=10.0,
                text="LectureAI Book",
                bounding_box=BoundingBox(x0=400.0, y0=30.0, x1=550.0, y1=45.0), # top 20%
            ),
            BlockSchema(
                block_id="b5",
                page_number=2,
                reading_order=2,
                block_type=BlockType.PARAGRAPH,
                text="2",
                bounding_box=BoundingBox(x0=300.0, y0=770.0, x1=310.0, y1=785.0), # bottom 20%
            ),
        ]
        doc = self.doc.model_copy()
        doc.pages = pages
        doc.blocks = input_blocks
        
        # Test Mode: Remove (Default)
        meta = ImmutableMetadata(upload_id="u123")
        context_remove = NormalizationContext(meta, debug_mode=True)
        res_remove = normalizer.run(doc, context_remove)
        
        # Expected: "Chapter 1 Introduction" remains (protected).
        # "LectureAI Book" removed on both pages (repeated header).
        # Page numbers "1" and "2" removed on both pages.
        self.assertEqual(len(res_remove.document.blocks), 1)
        self.assertEqual(res_remove.document.blocks[0].text, "Chapter 1 Introduction")
        self.assertEqual(res_remove.metrics.removed_blocks_count, 4)
        
        # Test Mode: Classify
        from app.core.config import settings
        old_mode = settings.HEADER_FOOTER_MODE
        try:
            settings.HEADER_FOOTER_MODE = "classify"
            context_classify = NormalizationContext(meta, debug_mode=True)
            res_classify = normalizer.run(doc, context_classify)
            
            # All blocks retained, but b2/b4 classified as HEADER, b3/b5 as PAGE_NUMBER
            blocks_out = res_classify.document.blocks
            self.assertEqual(len(blocks_out), 5)
            self.assertEqual(blocks_out[0].block_type, BlockType.PARAGRAPH) # protected chapter heading
            self.assertEqual(blocks_out[1].block_type, BlockType.HEADER) # LectureAI Book
            self.assertEqual(blocks_out[2].block_type, BlockType.PAGE_NUMBER) # 1
            self.assertEqual(blocks_out[3].block_type, BlockType.HEADER) # LectureAI Book
            self.assertEqual(blocks_out[4].block_type, BlockType.PAGE_NUMBER) # 2
        finally:
            settings.HEADER_FOOTER_MODE = old_mode


if __name__ == "__main__":
    unittest.main()
