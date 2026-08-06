from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from app.services.intelligence.annotations import BaseAnnotation


class TypographyFeatures(BaseModel):
    font_size: float
    font_family: str
    bold: bool
    italic: bool
    is_all_caps: bool
    is_title_case: bool
    starts_with_capital: bool
    ends_with_punctuation: bool


class GeometryFeatures(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float
    width: float
    height: float
    aspect_ratio: float
    page_position_y: float  # y0 / page_height
    margin_left: float
    margin_right: float
    indentation: float
    alignment: str  # "left", "right", "center", "justify"


class LayoutFeatures(BaseModel):
    line_spacing: float = 0.0
    paragraph_spacing_above: float = 0.0
    paragraph_spacing_below: float = 0.0
    column_index: int = 0
    total_columns_on_page: int = 1
    is_at_top: bool = False
    is_at_bottom: bool = False


class StatisticalFeatures(BaseModel):
    word_count: int
    char_count: int
    uppercase_ratio: float
    lowercase_ratio: float
    digit_ratio: float
    punctuation_ratio: float
    symbol_ratio: float
    avg_word_length: float
    text_density: float  # char_count / (width * height)


class ContextFeatures(BaseModel):
    prev_block_id: Optional[str] = None
    next_block_id: Optional[str] = None
    prev_block_text: Optional[str] = None
    next_block_text: Optional[str] = None
    prev_block_font_size: Optional[float] = None
    next_block_font_size: Optional[float] = None
    prev_block_type: Optional[str] = None
    next_block_type: Optional[str] = None
    parent_heading_id: Optional[str] = None


class BlockFeatures(BaseModel):
    typography: TypographyFeatures
    geometry: GeometryFeatures
    layout: LayoutFeatures
    statistical: StatisticalFeatures
    context: ContextFeatures


class FeatureAnnotation(BaseAnnotation):
    """Annotation class holding all calculated block features."""
    features: BlockFeatures
