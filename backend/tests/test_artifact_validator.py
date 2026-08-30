import pytest
from app.schemas.artifact import ArtifactPlan, SlideModel, SlideType
from app.services.artifact.artifact_validator import ArtifactValidator, ArtifactValidationContext, MAX_CONTENT_ITEMS, MAX_CHARS_PER_SLIDE, MAX_CHARS_PER_BULLET, MAX_TITLE_CHARS

@pytest.fixture
def valid_context():
    return ArtifactValidationContext(
        valid_node_ids={"unit_1", "topic_1", "concept_1"},
        valid_evidence_ids={"ev_1", "ev_2"},
        expected_units={"unit_1"},
        config={"include_examples": True, "include_questions": True}
    )

@pytest.fixture
def validator():
    return ArtifactValidator()

def test_valid_minimal_artifact_plan(validator, valid_context):
    plan = ArtifactPlan(slides=[
        SlideModel(
            slide_type=SlideType.TITLE,
            title="Valid Title Slide",
            content=[],
            source_node_ids=["unit_1"],
            evidence_ids=[]
        ),
        SlideModel(
            slide_type=SlideType.CONTENT,
            title="Valid Content Slide",
            content=["Bullet 1", "Bullet 2"],
            source_node_ids=["topic_1"],
            evidence_ids=["ev_1"]
        )
    ])
    result = validator.validate(plan, valid_context)
    assert result.is_valid is True
    assert len(result.errors) == 0

def test_empty_artifact_plan_fails(validator, valid_context):
    plan = ArtifactPlan(slides=[])
    result = validator.validate(plan, valid_context)
    assert result.is_valid is False
    assert any(e.category == "STRUCTURE" and "no slides" in e.message for e in result.errors)

def test_empty_slide_fails(validator, valid_context):
    plan = ArtifactPlan(slides=[
        SlideModel(
            slide_type=SlideType.CONTENT,
            title="Empty Content",
            content=["    ", ""], # whitespace only
            source_node_ids=["unit_1"]
        )
    ])
    result = validator.validate(plan, valid_context)
    assert result.is_valid is False
    assert any(e.category == "STRUCTURE" and "whitespace-only" in e.message for e in result.errors)
    
    plan2 = ArtifactPlan(slides=[
        SlideModel(
            slide_type=SlideType.CONTENT,
            title="  ", # empty title
            content=["Valid bullet"],
            source_node_ids=["unit_1"]
        )
    ])
    result2 = validator.validate(plan2, valid_context)
    assert result2.is_valid is False
    assert any(e.category == "STRUCTURE" and "title is empty" in e.message for e in result2.errors)

def test_overloaded_slide_fails(validator, valid_context):
    # Too many bullets
    plan_bullets = ArtifactPlan(slides=[
        SlideModel(
            slide_type=SlideType.CONTENT,
            title="Many bullets",
            content=[f"Bullet {i}" for i in range(MAX_CONTENT_ITEMS + 1)],
            source_node_ids=["unit_1"]
        )
    ])
    result_bullets = validator.validate(plan_bullets, valid_context)
    assert result_bullets.is_valid is False
    assert any(e.category == "DENSITY" and "Too many content items" in e.message for e in result_bullets.errors)
    
    # Too many chars
    plan_chars = ArtifactPlan(slides=[
        SlideModel(
            slide_type=SlideType.CONTENT,
            title="Long text",
            content=["A" * MAX_CHARS_PER_SLIDE],
            source_node_ids=["unit_1"]
        )
    ])
    result_chars = validator.validate(plan_chars, valid_context)
    assert result_chars.is_valid is False
    assert any(e.category == "DENSITY" and "Total slide characters exceed" in e.message for e in result_chars.errors)

def test_excessively_long_bullet_rejected(validator, valid_context):
    plan = ArtifactPlan(slides=[
        SlideModel(
            slide_type=SlideType.CONTENT,
            title="Title",
            content=["A" * (MAX_CHARS_PER_BULLET + 1)],
            source_node_ids=["unit_1"]
        )
    ])
    result = validator.validate(plan, valid_context)
    assert result.is_valid is False
    assert any(e.category == "DENSITY" and "Bullet exceeds maximum length" in e.message for e in result.errors)

def test_missing_required_unit_fails(validator):
    context = ArtifactValidationContext(
        valid_node_ids={"topic_1"},
        valid_evidence_ids=set(),
        expected_units={"unit_1"}, # Expects unit_1
        config={}
    )
    plan = ArtifactPlan(slides=[
        SlideModel(
            slide_type=SlideType.CONTENT,
            title="Some Topic",
            content=["Bullet"],
            source_node_ids=["topic_1"] # No unit_1
        )
    ])
    result = validator.validate(plan, context)
    assert result.is_valid is False
    assert any(e.category == "COVERAGE" and "Missing required unit" in e.message for e in result.errors)

def test_config_rejects_example_slides(validator, valid_context):
    valid_context.config["include_examples"] = False
    plan = ArtifactPlan(slides=[
        SlideModel(
            slide_type=SlideType.EXAMPLE,
            title="Example Slide",
            content=["Bullet"],
            source_node_ids=["unit_1"]
        )
    ])
    result = validator.validate(plan, valid_context)
    assert result.is_valid is False
    assert any(e.category == "CONFIGURATION" and "EXAMPLE slide generated" in e.message for e in result.errors)

def test_config_rejects_question_slides(validator, valid_context):
    valid_context.config["include_questions"] = False
    plan = ArtifactPlan(slides=[
        SlideModel(
            slide_type=SlideType.QUESTION,
            title="Question Slide",
            content=["Bullet"],
            source_node_ids=["unit_1"]
        )
    ])
    result = validator.validate(plan, valid_context)
    assert result.is_valid is False
    assert any(e.category == "CONFIGURATION" and "QUESTION slide generated" in e.message for e in result.errors)

def test_fabricated_source_node_id_fails(validator, valid_context):
    plan = ArtifactPlan(slides=[
        SlideModel(
            slide_type=SlideType.CONTENT,
            title="Content",
            content=["Bullet"],
            source_node_ids=["fake_node_123"]
        )
    ])
    result = validator.validate(plan, valid_context)
    assert result.is_valid is False
    assert any(e.category == "GROUNDING" and "fake_node_123" in e.message for e in result.errors)

def test_fabricated_evidence_id_fails(validator, valid_context):
    plan = ArtifactPlan(slides=[
        SlideModel(
            slide_type=SlideType.CONTENT,
            title="Content",
            content=["Bullet"],
            source_node_ids=["unit_1"],
            evidence_ids=["fake_evidence_123"]
        )
    ])
    result = validator.validate(plan, valid_context)
    assert result.is_valid is False
    assert any(e.category == "GROUNDING" and "fake_evidence_123" in e.message for e in result.errors)

def test_missing_provenance_factual_slide_fails(validator, valid_context):
    plan = ArtifactPlan(slides=[
        SlideModel(
            slide_type=SlideType.CONTENT,
            title="Content",
            content=["Bullet"],
            source_node_ids=[], # Missing!
            evidence_ids=[] # Missing!
        )
    ])
    result = validator.validate(plan, valid_context)
    assert result.is_valid is False
    assert any(e.category == "PROVENANCE" and "must have at least one" in e.message for e in result.errors)

def test_title_slide_no_grounding_passes(validator, valid_context):
    # Coverage check might fail if unit_1 is missing, so let's add a unit_1 reference somewhere
    plan = ArtifactPlan(slides=[
        SlideModel(
            slide_type=SlideType.TITLE,
            title="Title Slide",
            content=[],
            source_node_ids=[],
            evidence_ids=[]
        ),
        SlideModel(
            slide_type=SlideType.CONTENT,
            title="Content",
            content=["Bullet"],
            source_node_ids=["unit_1"]
        )
    ])
    result = validator.validate(plan, valid_context)
    assert result.is_valid is True

def test_validator_does_not_mutate_plan(validator, valid_context):
    plan = ArtifactPlan(slides=[
        SlideModel(
            slide_type=SlideType.CONTENT,
            title="Content",
            content=["Bullet"],
            source_node_ids=["unit_1"]
        )
    ])
    plan_copy = plan.model_copy(deep=True)
    validator.validate(plan, valid_context)
    assert plan.model_dump() == plan_copy.model_dump()
    
def test_validation_result_contains_diagnostics(validator, valid_context):
    plan = ArtifactPlan(slides=[
        SlideModel(
            slide_type=SlideType.CONTENT,
            title="Content",
            content=["Bullet"],
            source_node_ids=["fake_node"]
        )
    ])
    result = validator.validate(plan, valid_context)
    
    assert result.is_valid is False
    assert result.metrics["total_slides"] == 1
    assert result.metrics["total_errors"] == 2 # 1 Grounding, 1 Coverage (missing unit_1)
    
    err_grounding = next(e for e in result.errors if e.category == "GROUNDING")
    assert err_grounding.slide_index == 0
    assert "fake_node" in err_grounding.message
