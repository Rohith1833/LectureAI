import re
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from app.schemas.document import BlockSchema, BlockType
from app.services.intelligence.base import BaseIntelligenceModule, ModuleMetadata
from app.services.intelligence.context import IntelligenceContext
from app.services.intelligence.graph import DocumentGraph


class AcademicFeature(BaseModel):
    """Holds calculated pedagogical features for a single block schema."""
    block_id: str
    heading_depth: int
    typography_scale: float
    indentation_level: int
    semantic_label: BlockType
    preceding_neighbor_id: Optional[str] = None
    following_neighbor_id: Optional[str] = None
    enclosing_section_title: Optional[str] = None
    contains_mathematical_notation: bool = False
    syntactic_indicators: List[str] = Field(default_factory=list)


class AcademicFeatureEngine(BaseIntelligenceModule):
    """Pre-calculates academic layout and textual features to optimize subsequent classifications."""

    def __init__(self):
        self._metadata = ModuleMetadata(
            name="ACADEMIC_FEATURE_ENGINE",
            version="1.0.0",
            author="LectureAI Core",
            stage="academic_features_calculation",
            priority=125,
            dependencies=["DOCUMENT_QUALITY_MODULE"],
            enabled=True,
        )

    @property
    def metadata(self) -> ModuleMetadata:
        return self._metadata

    def initialize(self, config: dict) -> None:
        pass

    def execute(self, context: IntelligenceContext) -> None:
        doc = context.document
        if not doc or not doc.blocks:
            return

        # Fetch DocumentReadingGraphAnnotation
        from app.services.intelligence.graph import DocumentReadingGraphAnnotation
        from app.services.intelligence.annotations import ConfidenceScore
        
        graphs = context.annotation_store.find_by_type(DocumentReadingGraphAnnotation)
        graph_anno = graphs[0] if graphs else None
        
        if not graph_anno:
            graph_anno = DocumentReadingGraphAnnotation(
                annotation_id="temp_g",
                target_id=doc.upload_id,
                provenance="temp",
                confidence=ConfidenceScore(score=1.0),
                nodes=[b.block_id for b in doc.blocks],
                edges=[]
            )

        # Instantiate DocumentGraph navigation facade
        doc_graph = DocumentGraph(doc, graph_anno)
        feature_store: Dict[str, AcademicFeature] = {}

        # Keywords regex patterns
        math_symbols_regex = re.compile(r"[\u2200-\u22FF]|\b[xXyYzZ]\b|[\+\-\*\/\=\<\>\(\)]\s*[0-9]+|\b\d+\b\s*[\+\-\*\/\=]")
        indicators_map = {
            "starts_with_definition": re.compile(r"^(?:Definition|Def\.)\s+\d+", re.IGNORECASE),
            "starts_with_theorem": re.compile(r"^(?:Theorem|Thm\.)\s+\d+", re.IGNORECASE),
            "starts_with_proof": re.compile(r"^(?:Proof|Pf\.)\b", re.IGNORECASE),
            "starts_with_example": re.compile(r"^(?:Example|Ex\.)\s+\d+", re.IGNORECASE),
            "starts_with_exercise": re.compile(r"^(?:Exercise|Exer\.)\s+\d+", re.IGNORECASE),
            "starts_with_objective": re.compile(r"^(?:Learning Objectives?|Objectives?)\b", re.IGNORECASE),
            "starts_with_summary": re.compile(r"^(?:Summary|Key Takeaways?)\b", re.IGNORECASE),
        }

        # Build map for fast coordinate access
        blocks_map = {b.block_id: b for b in doc.blocks}

        for idx, block in enumerate(doc.blocks):
            # Calculate heading depth
            depth = 0
            curr_id = block.block_id
            while True:
                parent_node = doc_graph.get_parent(curr_id)
                if parent_node:
                    depth += 1
                    curr_id = parent_node.block_id
                else:
                    break

            # Typography scale
            font_size = getattr(block, "font_size", 10.0) or 10.0
            typography_scale = font_size / 10.0

            # Indentation
            indent = 0
            bbox = block.bounding_box
            if bbox and bbox.x0 > 50.0:
                indent = int((bbox.x0 - 50.0) / 15.0)

            # Neighbor IDs
            prec_id = doc.blocks[idx - 1].block_id if idx > 0 else None
            foll_id = doc.blocks[idx + 1].block_id if idx < len(doc.blocks) - 1 else None

            # Nearest enclosing section title
            enclosing_title = None
            curr_section = doc_graph.get_section(block.block_id)
            if curr_section:
                enclosing_title = curr_section.text

            # Syntactic indicators
            text = (block.text or "").strip()
            indicators = []
            for name, pattern in indicators_map.items():
                if pattern.match(text):
                    indicators.append(name)

            has_math = bool(math_symbols_regex.search(text))

            feature_store[block.block_id] = AcademicFeature(
                block_id=block.block_id,
                heading_depth=depth,
                typography_scale=typography_scale,
                indentation_level=indent,
                semantic_label=block.block_type,
                preceding_neighbor_id=prec_id,
                following_neighbor_id=foll_id,
                enclosing_section_title=enclosing_title,
                contains_mathematical_notation=has_math,
                syntactic_indicators=indicators,
            )

        # Persist features in shared context cache
        context.shared_cache["academic_features"] = feature_store
