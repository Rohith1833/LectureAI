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
from app.services.intelligence import (
    IntelligenceConfig,
    IntelligenceEngine,
    FeatureExtractionModule,
    ReadingOrderIntelligenceModule,
    HierarchyBuilderModule,
    DocumentReadingGraphAnnotation,
    DocumentGraph,
    HierarchyAnnotation,
)


from app.services.intelligence import (
    HeadingDetectionModule,
    ListQuoteNoteDetectionModule,
    TableCaptionDetectionModule,
    CodeFormulaDetectionModule,
)


class TestHierarchyBuilder(unittest.TestCase):

    def test_hierarchy_tree_and_graph(self):
        """Verify stack-based hierarchy nesting, caption-target mapping, metadata spans, and DocumentGraph walks."""
        config = IntelligenceConfig()
        engine = IntelligenceEngine(config)

        # Mock modules
        feat_mod = FeatureExtractionModule()
        heading_mod = HeadingDetectionModule()
        lqn_mod = ListQuoteNoteDetectionModule()
        tc_mod = TableCaptionDetectionModule()
        cf_mod = CodeFormulaDetectionModule()
        ro_mod = ReadingOrderIntelligenceModule()
        hb_mod = HierarchyBuilderModule()

        # Build mock document
        pages = [PageSchema(page_number=1, width=600.0, height=800.0)]
        blocks = [
            # H1 Chapter Heading
            BlockSchema(
                block_id="b_h1",
                page_number=1,
                reading_order=0,
                block_type=BlockType.HEADING,
                heading_level=1,
                font_family="Arial",
                font_size=20.0,
                bold=True,
                text="Chapter 1: Intro",
                bounding_box=BoundingBox(x0=50.0, y0=50.0, x1=300.0, y1=80.0),
            ),
            # H3 Subsection Heading (Skipped level check: H1 -> H3)
            BlockSchema(
                block_id="b_h3",
                page_number=1,
                reading_order=1,
                block_type=BlockType.HEADING,
                heading_level=3,
                font_family="Arial",
                font_size=14.0,
                bold=True,
                text="1.1.1 Math",
                bounding_box=BoundingBox(x0=50.0, y0=100.0, x1=250.0, y1=120.0),
            ),
            # Paragraph under H3
            BlockSchema(
                block_id="b_para",
                page_number=1,
                reading_order=2,
                block_type=BlockType.PARAGRAPH,
                font_family="Arial",
                font_size=10.0,
                text="Standard textbook body paragraph text.",
                bounding_box=BoundingBox(x0=50.0, y0=140.0, x1=550.0, y1=160.0),
            ),
            # Table block
            BlockSchema(
                block_id="b_table",
                page_number=1,
                reading_order=3,
                block_type=BlockType.TABLE,
                font_family="Arial",
                font_size=10.0,
                text="ColA   ColB\nValA   ValB",
                bounding_box=BoundingBox(x0=50.0, y0=180.0, x1=400.0, y1=240.0),
            ),
            # Caption block associated with table
            BlockSchema(
                block_id="b_caption",
                page_number=1,
                reading_order=4,
                block_type=BlockType.CAPTION,
                font_family="Arial",
                font_size=9.0,
                text="Table 1.1: Statistical layout counts",
                bounding_box=BoundingBox(x0=50.0, y0=250.0, x1=400.0, y1=265.0),
            ),
        ]

        doc = DocumentExtractionResult(
            upload_id="test_hb_class",
            status="processed",
            metadata=DocumentMetadataSchema(page_count=1),
            pages=pages,
            blocks=blocks,
            tables=[],
            images=[],
            extraction_timestamp="t",
            processing_time=0.0,
        )

        # Run pipeline
        context, report = engine.execute(
            document=doc,
            page_metadata={1: pages[0]},
            document_metadata=doc.metadata,
            modules=[hb_mod, ro_mod, cf_mod, tc_mod, lqn_mod, heading_mod, feat_mod],
            upload_id="test_hb_class",
        )

        self.assertTrue(report.success)
        self.assertEqual(
            report.execution_order,
            [
                "FEATURE_EXTRACTION_MODULE",
                "HEADING_DETECTION_MODULE",
                "READING_ORDER_INTELLIGENCE_MODULE",
                "LIST_QUOTE_NOTE_DETECTION_MODULE",
                "TABLE_CAPTION_DETECTION_MODULE",
                "CODE_FORMULA_DETECTION_MODULE",
                "HIERARCHY_BUILDER_MODULE",
            ]
        )

        # 1. Assert Parent-Child linkages
        # H3 subsection's parent is H1 (skipped level H2 handled)
        self.assertEqual(doc.blocks[1].parent_block_id, "b_h1")
        # Paragraph's parent is H3
        self.assertEqual(doc.blocks[2].parent_block_id, "b_h3")
        # Table parent is H3
        self.assertEqual(doc.blocks[3].parent_block_id, "b_h3")
        # Caption parent is Table block (caption target association)
        self.assertEqual(doc.blocks[4].parent_block_id, "b_table")

        # 2. Query HierarchyAnnotations
        store = context.annotation_store
        h_annos = store.find_by_type(HierarchyAnnotation)
        self.assertEqual(len(h_annos), 5)
        anno_map = {a.target_id: a for a in h_annos}

        # Assert Metadata Spans
        h_h1 = anno_map["b_h1"]
        self.assertEqual(h_h1.metadata["depth"], 0)
        self.assertEqual(h_h1.metadata["subtree_size"], 5)  # H1 + 4 children/descendants
        self.assertEqual(h_h1.metadata["first_descendant"], "b_h3")
        self.assertEqual(h_h1.metadata["last_descendant"], "b_caption")

        h_h3 = anno_map["b_h3"]
        self.assertEqual(h_h3.metadata["depth"], 1)
        self.assertEqual(h_h3.metadata["chapter_id"], "b_h1")
        self.assertEqual(h_h3.metadata["section_id"], "b_h3")

        # 3. Assert Navigation Wrapper (DocumentGraph API)
        graphs = store.find_by_type(DocumentReadingGraphAnnotation)
        self.assertEqual(len(graphs), 1)
        
        doc_graph = DocumentGraph(doc, graphs[0])

        self.assertEqual(doc_graph.get_parent("b_h3").block_id, "b_h1")
        self.assertEqual(
            [c.block_id for c in doc_graph.get_children("b_h3")],
            ["b_para", "b_table"]
        )
        self.assertEqual(doc_graph.get_next("b_para").block_id, "b_table")
        self.assertEqual(doc_graph.get_previous("b_table").block_id, "b_para")

        # Ancestors path
        self.assertEqual(
            [a.block_id for a in doc_graph.get_ancestors("b_para")],
            ["b_h3", "b_h1"]
        )

        # Subtree descendants
        self.assertEqual(
            [d.block_id for d in doc_graph.get_descendants("b_h3")],
            ["b_para", "b_table", "b_caption"]
        )

        # Section lookup
        self.assertEqual(doc_graph.get_section("b_para").block_id, "b_h3")
        self.assertEqual(doc_graph.get_section("b_h3").block_id, "b_h3")

        # Document breadcrumbs path
        self.assertEqual(
            doc_graph.get_document_path("b_para"),
            ["Chapter 1: Intro", "1.1.1 Math"]
        )


if __name__ == "__main__":
    unittest.main()
