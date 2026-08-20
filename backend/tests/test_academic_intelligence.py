import unittest
from typing import List

from app.schemas.document import (
    DocumentExtractionResult,
    DocumentMetadataSchema,
    PageSchema,
    BlockSchema,
    BlockType,
    BoundingBox,
)
from app.schemas.academic import AcademicNodeCategory
from app.services.intelligence import (
    IntelligenceConfig,
    IntelligenceEngine,
    FeatureExtractionModule,
    HeadingDetectionModule,
    ListQuoteNoteDetectionModule,
    TableCaptionDetectionModule,
    CodeFormulaDetectionModule,
    ReadingOrderIntelligenceModule,
    HierarchyBuilderModule,
    HierarchyValidationModule,
    DocumentQualityModule,
    AcademicFeatureEngine,
    CurriculumClassificationModule,
    ExpositoryClassificationModule,
    PedagogicalClassificationModule,
    AcademicGraphBuilderModule,
    AcademicQualityModule,
    QualityAnnotation,
)


class TestAcademicIntelligence(unittest.TestCase):

    def test_academic_intelligence_pipeline(self):
        """Verify academic feature engine calculation, node classifiers, graph builder, and validation metrics."""
        config = IntelligenceConfig()
        engine = IntelligenceEngine(config)

        # Pipeline modules list including Phase 4 and all new Phase 5A modules
        modules = [
            FeatureExtractionModule(),
            HeadingDetectionModule(),
            ListQuoteNoteDetectionModule(),
            TableCaptionDetectionModule(),
            CodeFormulaDetectionModule(),
            ReadingOrderIntelligenceModule(),
            HierarchyBuilderModule(),
            HierarchyValidationModule(),
            DocumentQualityModule(),
            AcademicFeatureEngine(),
            CurriculumClassificationModule(),
            ExpositoryClassificationModule(),
            PedagogicalClassificationModule(),
            AcademicGraphBuilderModule(),
            AcademicQualityModule(),
        ]

        pages = [PageSchema(page_number=1, width=600.0, height=800.0)]
        blocks = [
            # Heading 1 (depth=0, maps to Unit/Chapter)
            BlockSchema(
                block_id="b_ch1",
                page_number=1,
                reading_order=0,
                block_type=BlockType.HEADING,
                heading_level=1,
                font_family="Arial",
                font_size=24.0,
                bold=True,
                text="Chapter 1: Principles of Computation",
                bounding_box=BoundingBox(x0=50.0, y0=50.0, x1=400.0, y1=85.0),
            ),
            # Heading 2 (depth=1, maps to Section)
            BlockSchema(
                block_id="b_sec1",
                page_number=1,
                reading_order=1,
                block_type=BlockType.HEADING,
                heading_level=2,
                font_family="Arial",
                font_size=18.0,
                bold=True,
                text="1.1 Turing Machines",
                bounding_box=BoundingBox(x0=50.0, y0=100.0, x1=350.0, y1=130.0),
            ),
            # Sub-heading 3 (depth=2, maps to Section)
            BlockSchema(
                block_id="b_subsec1",
                page_number=1,
                reading_order=2,
                block_type=BlockType.HEADING,
                heading_level=3,
                font_family="Arial",
                font_size=14.0,
                bold=True,
                text="1.1.1 Finite State Controls",
                bounding_box=BoundingBox(x0=50.0, y0=135.0, x1=300.0, y1=155.0),
            ),
            # Definition block (Expository element)
            BlockSchema(
                block_id="b_def",
                page_number=1,
                reading_order=3,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=10.0,
                text="Definition 1.1: A Turing Machine is a mathematical model of computation.",
                bounding_box=BoundingBox(x0=50.0, y0=165.0, x1=550.0, y1=205.0),
            ),
            # Summary block (Pedagogical element)
            BlockSchema(
                block_id="b_sum",
                page_number=1,
                reading_order=4,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=10.0,
                text="Summary: In conclusion, computing bounds are finite.",
                bounding_box=BoundingBox(x0=50.0, y0=215.0, x1=550.0, y1=245.0),
            ),
        ]

        doc = DocumentExtractionResult(
            upload_id="test_academic_upload",
            status="processed",
            metadata=DocumentMetadataSchema(page_count=1),
            pages=pages,
            blocks=blocks,
            tables=[],
            images=[],
            extraction_timestamp="t",
            processing_time=0.0,
        )

        # Execute DAG E2E
        context, report = engine.execute(
            document=doc,
            page_metadata={1: pages[0]},
            document_metadata=doc.metadata,
            modules=modules,
            upload_id="test_academic_upload",
        )

        self.assertTrue(report.success)
        from app.services.intelligence.graph import DocumentReadingGraphAnnotation
        self.assertEqual(report.execution_order[-1], "ACADEMIC_QUALITY_MODULE")

        # 1. Assert AcademicFeatureEngine populated features
        feature_store = context.shared_cache.get("academic_features")
        self.assertIsNotNone(feature_store)
        self.assertIn("b_ch1", feature_store)
        self.assertEqual(feature_store["b_ch1"].typography_scale, 2.4)
        self.assertIn("starts_with_definition", feature_store["b_def"].syntactic_indicators)
        self.assertIn("starts_with_summary", feature_store["b_sum"].syntactic_indicators)

        # 2. Assert AcademicGraphBuilder constructed nodes and containment edges
        graph_data = context.shared_cache.get("academic_graph")
        self.assertIsNotNone(graph_data)
        nodes = graph_data["nodes"]
        edges = graph_data["edges"]

        self.assertEqual(len(nodes), 5)
        categories = [n.category for n in nodes]
        self.assertIn(AcademicNodeCategory.UNIT, categories)
        self.assertIn(AcademicNodeCategory.CHAPTER, categories)
        self.assertIn(AcademicNodeCategory.SECTION, categories)
        self.assertIn(AcademicNodeCategory.DEFINITION, categories)
        self.assertIn(AcademicNodeCategory.SUMMARY, categories)

        # Check containment edges constructed using DocumentGraph hierarchy (Definition -> Section -> Chapter)
        edge_types = [e.edge_type for e in edges]
        self.assertIn("CONTAINS", edge_types)

        # 3. Assert AcademicQualityMetrics compiled and mapped
        self.assertIsNotNone(report.academic_quality_score)
        self.assertIsNotNone(report.academic_coverage_score)
        self.assertIsNotNone(report.academic_density_score)
        self.assertEqual(report.academic_orphan_count, 0)
        self.assertTrue(report.academic_quality_score > 0.0)


if __name__ == "__main__":
    unittest.main()
