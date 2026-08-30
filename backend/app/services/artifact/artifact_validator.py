from typing import List, Dict, Any, Set, Optional
from pydantic import BaseModel, Field
from app.schemas.artifact import ArtifactPlan, SlideModel, SlideType

# Constants for density validation
MAX_CONTENT_ITEMS = 7
MAX_CHARS_PER_SLIDE = 800
MAX_CHARS_PER_BULLET = 250
MAX_TITLE_CHARS = 120
WARN_CHARS_PER_SLIDE = 600

class ArtifactValidationError(BaseModel):
    slide_index: Optional[int]
    category: str
    message: str

class ArtifactValidationResult(BaseModel):
    is_valid: bool = True
    errors: List[ArtifactValidationError] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)

class ArtifactValidationContext(BaseModel):
    valid_node_ids: Set[str]
    valid_evidence_ids: Set[str]
    expected_units: Set[str]
    config: Dict[str, Any]

class ArtifactValidator:
    """
    Phase 9D: Deterministic, offline validation layer for ArtifactPlans.
    Validates structure, density, coverage, configuration compliance, and grounding.
    """
    
    def validate(self, plan: ArtifactPlan, context: ArtifactValidationContext) -> ArtifactValidationResult:
        result = ArtifactValidationResult()
        
        # 1. Structure (Plan-level)
        if not plan.slides:
            self._add_error(result, None, "STRUCTURE", "ArtifactPlan contains no slides.")
            result.is_valid = False
            return result
            
        # Coverage tracking
        found_units = set()
            
        for i, slide in enumerate(plan.slides):
            # 2. Structure (Slide-level)
            self._validate_slide_structure(slide, i, result)
            
            # 3. Density / Text Safety
            self._validate_slide_density(slide, i, result)
            
            # 4. Configuration Compliance
            self._validate_slide_config(slide, i, context.config, result)
            
            # 5. Grounding & Provenance
            self._validate_slide_grounding(slide, i, context, result)
            
            # Record found units for coverage (assume source_node_ids could include units)
            for sid in slide.source_node_ids:
                if sid in context.expected_units:
                    found_units.add(sid)
                    
        # 6. Academic Coverage Validation
        for expected_unit in context.expected_units:
            if expected_unit not in found_units:
                self._add_error(result, None, "COVERAGE", f"Missing required unit '{expected_unit}' in the plan.")
                
        # Final validity check
        if len(result.errors) > 0:
            result.is_valid = False
            
        # Metrics
        result.metrics["total_slides"] = len(plan.slides)
        result.metrics["total_errors"] = len(result.errors)
        result.metrics["total_warnings"] = len(result.warnings)
            
        return result

    def _add_error(self, result: ArtifactValidationResult, slide_index: Optional[int], category: str, message: str):
        result.errors.append(ArtifactValidationError(
            slide_index=slide_index,
            category=category,
            message=message
        ))

    def _validate_slide_structure(self, slide: SlideModel, index: int, result: ArtifactValidationResult):
        # Must have a title for most slides, except maybe purely decorative ones, but we enforce title on all for now.
        if not slide.title or slide.title.strip() == "":
            self._add_error(result, index, "STRUCTURE", "Slide title is empty or whitespace-only.")
            
        # Must have content if not a TITLE slide
        if slide.slide_type != SlideType.TITLE:
            if not slide.content:
                self._add_error(result, index, "STRUCTURE", f"Slide of type {slide.slide_type.value} must have content.")
            else:
                has_meaningful_content = any(c and c.strip() != "" for c in slide.content)
                if not has_meaningful_content:
                    self._add_error(result, index, "STRUCTURE", "Slide content is whitespace-only.")

    def _validate_slide_density(self, slide: SlideModel, index: int, result: ArtifactValidationResult):
        if len(slide.content) > MAX_CONTENT_ITEMS:
            self._add_error(result, index, "DENSITY", f"Too many content items: {len(slide.content)} > {MAX_CONTENT_ITEMS}.")
            
        if len(slide.title) > MAX_TITLE_CHARS:
            self._add_error(result, index, "DENSITY", f"Title exceeds maximum length: {len(slide.title)} > {MAX_TITLE_CHARS}.")
            
        total_chars = len(slide.title)
        for bullet in slide.content:
            bullet_len = len(bullet)
            total_chars += bullet_len
            if bullet_len > MAX_CHARS_PER_BULLET:
                self._add_error(result, index, "DENSITY", f"Bullet exceeds maximum length: {bullet_len} > {MAX_CHARS_PER_BULLET}.")
                
        if total_chars > MAX_CHARS_PER_SLIDE:
            self._add_error(result, index, "DENSITY", f"Total slide characters exceed maximum: {total_chars} > {MAX_CHARS_PER_SLIDE}.")
        elif total_chars > WARN_CHARS_PER_SLIDE:
            result.warnings.append(f"Slide {index} is nearing character density limits ({total_chars} chars).")

    def _validate_slide_config(self, slide: SlideModel, index: int, config: Dict[str, Any], result: ArtifactValidationResult):
        include_examples = config.get("include_examples", True)
        include_questions = config.get("include_questions", True)
        
        if not include_examples and slide.slide_type == SlideType.EXAMPLE:
            self._add_error(result, index, "CONFIGURATION", "EXAMPLE slide generated when include_examples is False.")
            
        if not include_questions and slide.slide_type == SlideType.QUESTION:
            self._add_error(result, index, "CONFIGURATION", "QUESTION slide generated when include_questions is False.")

    def _validate_slide_grounding(self, slide: SlideModel, index: int, context: ArtifactValidationContext, result: ArtifactValidationResult):
        # 1. source_node_ids
        for sid in slide.source_node_ids:
            if sid not in context.valid_node_ids:
                self._add_error(result, index, "GROUNDING", f"Invalid or fabricated source_node_id: '{sid}'.")
                
        # 2. evidence_ids
        for eid in slide.evidence_ids:
            if eid not in context.valid_evidence_ids:
                self._add_error(result, index, "GROUNDING", f"Invalid or fabricated evidence_id: '{eid}'.")
                
        # 3. Provenance completeness (Factual slides must have some grounding)
        if slide.slide_type in (SlideType.CONTENT, SlideType.CONCEPT, SlideType.EXAMPLE):
            if not slide.source_node_ids and not slide.evidence_ids:
                self._add_error(result, index, "PROVENANCE", f"Factual slide of type {slide.slide_type.value} must have at least one source_node_id or evidence_id.")
