import pytest
import uuid
import json

from app.schemas.artifact import ArtifactJobRead, ArtifactStatus, ArtifactType
from app.schemas.academic import AcademicNodeCategory
from app.schemas.knowledge import (
    KnowledgeEntitySchema,
    KnowledgeVersionSchema,
    KnowledgeRelationshipSchema,
    KnowledgeRelationshipType,
    KnowledgeEvidenceSchema
)
from app.schemas.retrieval import RetrievalResult, RetrievedEntity, PassageSchema, RetrievalScope, RetrievalProvenance
from app.services.generation.base import LLMGenerationResponse
from app.services.generation.errors import GroundingValidationError
from app.services.artifact.artifact_planner import ArtifactPlanner
from unittest.mock import AsyncMock, MagicMock

# Mocks
class MockKnowledgeRepo:
    def __init__(self, version_schema: KnowledgeVersionSchema):
        self.version = version_schema

    def get_version(self, version_id: str):
        return self.version

class MockRetrievalService:
    def __init__(self, result: RetrievalResult):
        self.result = result

    def retrieve(self, request):
        return self.result

@pytest.fixture
def base_knowledge():
    unit_id = str(uuid.uuid4())
    topic_id = str(uuid.uuid4())
    
    unit = KnowledgeEntitySchema(
        id=unit_id,
        knowledge_version_id="kv1",
        entity_type=AcademicNodeCategory.UNIT,
        title="Unit 1",
        content="Unit Content",
        stable_id="s1"
    )
    topic = KnowledgeEntitySchema(
        id=topic_id,
        knowledge_version_id="kv1",
        entity_type=AcademicNodeCategory.TOPIC,
        title="Topic 1",
        content="Topic Content",
        stable_id="s2"
    )
    
    rel = KnowledgeRelationshipSchema(
        id="r1",
        knowledge_version_id="kv1",
        source_entity_id=unit_id,
        target_entity_id=topic_id,
        relationship_type=KnowledgeRelationshipType.CONTAINS
    )
    
    kv = KnowledgeVersionSchema(
        id="kv1",
        upload_id="u1",
        snapshot_id="snap1",
        entities=[unit, topic],
        relationships=[rel]
    )
    return kv, unit_id, topic_id

@pytest.fixture
def base_job():
    return ArtifactJobRead(
        id="job1",
        upload_id="u1",
        knowledge_version_id="kv1",
        artifact_type=ArtifactType.PPTX,
        status=ArtifactStatus.PLANNING,
        config={
            "include_examples": True,
            "include_questions": True,
            "audience_level": "beginner"
        },
        created_at="2023-01-01T00:00:00Z",
        updated_at="2023-01-01T00:00:00Z"
    )

@pytest.mark.asyncio
async def test_planner_success(base_knowledge, base_job):
    kv, unit_id, topic_id = base_knowledge
    
    mock_llm_json = {
        "slides": [
            {
                "slide_type": "TITLE",
                "title": "Welcome to Unit 1",
                "content": ["Introduction"],
                "source_node_ids": [unit_id],
                "evidence_ids": []
            }
        ]
    }
    llm_provider = AsyncMock()
    llm_provider.generate.return_value = LLMGenerationResponse(
        raw_response="",
        structured_output=mock_llm_json,
        model_name="mock"
    )
    
    # Empty retrieval result is fine because the unit_id is added to supplied sources directly from the chunk hierarchy
    retrieval_result = RetrievalResult(
        query="test",
        scope=RetrievalScope(document_id="u1", version_id="kv1"),
        provenance=RetrievalProvenance(knowledge_version_id="kv1", approval_version=1, document_id="u1", strategy_used="LEXICAL", total_candidates_considered=0),
        entities=[],
        total_entity_count=0,
        has_more=False
    )
    
    planner = ArtifactPlanner(
        knowledge_repo=MockKnowledgeRepo(kv),
        retrieval_service=MockRetrievalService(retrieval_result),
        llm_provider=llm_provider
    )
    
    plan = await planner.plan(base_job)
    
    assert len(plan.slides) == 1
    assert plan.slides[0].title == "Welcome to Unit 1"
    assert plan.slides[0].source_node_ids == [unit_id]

@pytest.mark.asyncio
async def test_planner_fails_on_fabricated_source(base_knowledge, base_job):
    kv, unit_id, topic_id = base_knowledge
    
    mock_llm_json = {
        "slides": [
            {
                "slide_type": "CONTENT",
                "title": "Bad Source",
                "content": ["Bad"],
                "source_node_ids": ["fabricated_id_123"],
                "evidence_ids": []
            }
        ]
    }
    llm_provider = AsyncMock()
    llm_provider.generate.return_value = LLMGenerationResponse(
        raw_response="",
        structured_output=mock_llm_json,
        model_name="mock"
    )
    retrieval_result = RetrievalResult(
        query="test",
        scope=RetrievalScope(document_id="u1", version_id="kv1"),
        provenance=RetrievalProvenance(knowledge_version_id="kv1", approval_version=1, document_id="u1", strategy_used="LEXICAL", total_candidates_considered=0),
        entities=[],
        total_entity_count=0,
        has_more=False
    )
    
    planner = ArtifactPlanner(
        knowledge_repo=MockKnowledgeRepo(kv),
        retrieval_service=MockRetrievalService(retrieval_result),
        llm_provider=llm_provider
    )
    
    with pytest.raises(GroundingValidationError) as exc:
        await planner.plan(base_job)
    assert "Fabricated source_node_id" in str(exc.value)

@pytest.mark.asyncio
async def test_planner_honors_config(base_knowledge, base_job):
    kv, unit_id, topic_id = base_knowledge
    
    base_job.config["include_examples"] = False
    
    mock_llm_json = {
        "slides": [
            {
                "slide_type": "EXAMPLE",
                "title": "An Example",
                "content": ["123"],
                "source_node_ids": [unit_id],
                "evidence_ids": []
            }
        ]
    }
    llm_provider = AsyncMock()
    llm_provider.generate.return_value = LLMGenerationResponse(
        raw_response="",
        structured_output=mock_llm_json,
        model_name="mock"
    )
    retrieval_result = RetrievalResult(
        query="test",
        scope=RetrievalScope(document_id="u1", version_id="kv1"),
        provenance=RetrievalProvenance(knowledge_version_id="kv1", approval_version=1, document_id="u1", strategy_used="LEXICAL", total_candidates_considered=0),
        entities=[],
        total_entity_count=0,
        has_more=False
    )
    
    planner = ArtifactPlanner(
        knowledge_repo=MockKnowledgeRepo(kv),
        retrieval_service=MockRetrievalService(retrieval_result),
        llm_provider=llm_provider
    )
    
    with pytest.raises(GroundingValidationError) as exc:
        await planner.plan(base_job)
    assert "EXAMPLE slide when include_examples is False" in str(exc.value)

@pytest.mark.asyncio
async def test_planner_subdivides_large_unit(base_job):
    # Create a large hierarchy: 1 Unit, 3 Topics, each with 4 Concepts (13 entities total, > MAX_ENTITIES_PER_CHUNK of 10)
    entities = []
    rels = []
    
    unit_id = "u1_large"
    entities.append(KnowledgeEntitySchema(
        id=unit_id, knowledge_version_id="kv1", entity_type=AcademicNodeCategory.UNIT, title="Large Unit", content="...", stable_id="s_u"
    ))
    
    for t_idx in range(3):
        t_id = f"t{t_idx}"
        entities.append(KnowledgeEntitySchema(
            id=t_id, knowledge_version_id="kv1", entity_type=AcademicNodeCategory.TOPIC, title=f"Topic {t_idx}", content="...", stable_id=f"s_{t_id}"
        ))
        rels.append(KnowledgeRelationshipSchema(
            id=f"r_u_t{t_idx}", knowledge_version_id="kv1", source_entity_id=unit_id, target_entity_id=t_id, relationship_type=KnowledgeRelationshipType.CONTAINS
        ))
        
        for c_idx in range(4):
            c_id = f"c{t_idx}_{c_idx}"
            entities.append(KnowledgeEntitySchema(
                id=c_id, knowledge_version_id="kv1", entity_type=AcademicNodeCategory.CONCEPT, title=f"Concept {c_idx}", content="...", stable_id=f"s_{c_id}"
            ))
            rels.append(KnowledgeRelationshipSchema(
                id=f"r_t{t_idx}_c{c_id}", knowledge_version_id="kv1", source_entity_id=t_id, target_entity_id=c_id, relationship_type=KnowledgeRelationshipType.CONTAINS
            ))
            
    kv = KnowledgeVersionSchema(id="kv1", upload_id="u1", snapshot_id="snap1", entities=entities, relationships=rels)
    
    mock_llm_json = {
        "slides": [
            {
                "slide_type": "TITLE",
                "title": "Welcome",
                "content": ["Introduction"],
                "source_node_ids": [unit_id],
                "evidence_ids": []
            }
        ]
    }
    llm_provider = AsyncMock()
    llm_provider.generate.return_value = LLMGenerationResponse(
        raw_response="",
        structured_output=mock_llm_json,
        model_name="mock"
    )
    
    retrieval_result = RetrievalResult(
        query="test",
        scope=RetrievalScope(document_id="u1", version_id="kv1"),
        provenance=RetrievalProvenance(knowledge_version_id="kv1", approval_version=1, document_id="u1", strategy_used="LEXICAL", total_candidates_considered=0),
        entities=[],
        total_entity_count=0,
        has_more=False
    )
    
    planner = ArtifactPlanner(
        knowledge_repo=MockKnowledgeRepo(kv),
        retrieval_service=MockRetrievalService(retrieval_result),
        llm_provider=llm_provider
    )
    
    plan = await planner.plan(base_job)
    
    # 1 Unit + (3 * 5) = 16 entities.
    # Chunk 1: Unit + Topic0 (1+4) + Topic1 (1+4) = 11 entities > 10. Saved chunk.
    # Chunk 2: Unit + Topic2 (1+4) = 6 entities. Saved chunk.
    # So we expect 2 LLM calls and 2 resulting slides total.
    assert llm_provider.generate.call_count == 2
    assert len(plan.slides) == 2
