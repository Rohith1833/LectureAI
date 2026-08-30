from typing import List, Dict, Any, Optional
import json

from loguru import logger
from app.schemas.artifact import ArtifactJobRead, ArtifactPlan, SlideModel, SlideType
from app.schemas.academic import AcademicNodeCategory
from app.schemas.knowledge import KnowledgeEntitySchema
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.retrieval.retrieval_service import RetrievalService
from app.schemas.retrieval import RetrievalRequest, RetrievalScope, RetrievalOptions
from app.services.generation.base import LLMProvider, LLMGenerationRequest
from app.services.generation.errors import GroundingValidationError

# Define a strict JSON schema for LLM structured output
SLIDE_FRAGMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "slides": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "slide_type": {
                        "type": "string", 
                        "enum": ["TITLE", "CONTENT", "CONCEPT", "EXAMPLE", "QUESTION"]
                    },
                    "title": {"type": "string"},
                    "content": {
                        "type": "array", 
                        "items": {"type": "string"}
                    },
                    "speaker_notes": {"type": "string"},
                    "source_node_ids": {
                        "type": "array", 
                        "items": {"type": "string"}
                    },
                    "evidence_ids": {
                        "type": "array", 
                        "items": {"type": "string"}
                    }
                },
                "required": ["slide_type", "title", "content", "source_node_ids", "evidence_ids"],
                "additionalProperties": False
            }
        }
    },
    "required": ["slides"],
    "additionalProperties": False
}


class ArtifactPlanner:
    """
    Hierarchical AI Generation Planning (Phase 9C).
    Converts a FINALIZED academic knowledge version into a structured, grounded ArtifactPlan.
    """

    def __init__(
        self,
        knowledge_repo: KnowledgeRepository,
        retrieval_service: RetrievalService,
        llm_provider: LLMProvider
    ):
        self.knowledge_repo = knowledge_repo
        self.retrieval_service = retrieval_service
        self.llm_provider = llm_provider

    async def plan(self, job: ArtifactJobRead) -> ArtifactPlan:
        """
        Executes bounded hierarchical chunking and deterministic merging to produce the ArtifactPlan.
        """
        logger.info(f"ArtifactPlanner starting for job {job.id}, knowledge_version={job.knowledge_version_id}")

        # 1. Fetch entire hierarchy from finalized version
        version = self.knowledge_repo.get_finalized_version(job.knowledge_version_id)
        if not version:
            raise ValueError(f"Knowledge version {job.knowledge_version_id} not found.")

        # Group entities logically
        units = []
        entity_map = {}
        for entity in version.entities:
            entity_map[entity.id] = entity
            if entity.entity_type == AcademicNodeCategory.UNIT:
                units.append(entity)

        if not units:
            raise ValueError("No academic units found in knowledge version.")

        # 2. Build chunks
        # Simple bounded chunking: For this implementation, we chunk by Unit.
        # If a Unit is extremely large, we could split by Topic, but preserving Unit->Topic deterministic order
        # is achieved easily by chunking at the Unit level and passing the nested Topics as context.
        # We will bound it by chunking per UNIT.
        
        # Configuration
        include_examples = job.config.get("include_examples", True)
        include_questions = job.config.get("include_questions", True)
        audience_level = job.config.get("audience_level", "general")
        depth = job.config.get("depth", "standard")
        
        # Extract desired unit count to plan (for subsets)
        num_units = job.config.get("num_units")
        if num_units and num_units < len(units):
            units = units[:num_units]

        final_plan = ArtifactPlan(slides=[])
        
        for unit in units:
            logger.debug(f"Planning chunk for Unit: {unit.title}")
            
            # 2. Build chunks
            MAX_ENTITIES_PER_CHUNK = 10
            
            # Find all topics for this unit
            topics = []
            for rel in version.relationships:
                if rel.source_entity_id == unit.id and rel.relationship_type.value == "CONTAINS":
                    target = entity_map.get(rel.target_entity_id)
                    if target and target.entity_type == AcademicNodeCategory.TOPIC:
                        topics.append(target)
            
            if not topics:
                chunks = [[unit]]
            else:
                chunks = []
                current_chunk = [unit]
                
                for topic in topics:
                    topic_entities = [topic]
                    for rel in version.relationships:
                        if rel.source_entity_id == topic.id and rel.relationship_type.value == "CONTAINS":
                            target = entity_map.get(rel.target_entity_id)
                            if target and target.entity_type == AcademicNodeCategory.CONCEPT:
                                topic_entities.append(target)
                    
                    if len(current_chunk) + len(topic_entities) - 1 > MAX_ENTITIES_PER_CHUNK and len(current_chunk) > 1:
                        chunks.append(current_chunk)
                        current_chunk = [unit]
                        
                    current_chunk.extend(topic_entities)
                
                if len(current_chunk) > 1 or len(chunks) == 0:
                    chunks.append(current_chunk)

            for chunk_idx, chunk_entities in enumerate(chunks):
                logger.debug(f"Planning chunk {chunk_idx+1}/{len(chunks)} for Unit: {unit.title} (size: {len(chunk_entities)})")
            
                # 3. Retrieval
                # Formulate query summarizing the chunk to get passage evidence
                chunk_titles = [e.title for e in chunk_entities]
                query = " ".join(chunk_titles[:5]) # Top N titles for lexical seed
                
                retrieval_request = RetrievalRequest(
                    query=query,
                    scope=RetrievalScope(
                        document_id=job.upload_id,
                        version_id=job.knowledge_version_id
                    ),
                    options=RetrievalOptions(
                        strategy="LEXICAL",
                        top_k=50,
                        include_evidence=True,
                        include_passages=True,
                        include_relationships=True
                    )
                )
                
                retrieval_result = self.retrieval_service.retrieve(retrieval_request)
                
                # Gather strictly supplied grounding references
                supplied_source_node_ids = set()
                supplied_evidence_ids = set()
                
                context_blocks = []
                context_blocks.append("## Academic Hierarchy Context")
                for e in chunk_entities:
                    supplied_source_node_ids.add(e.id)
                    context_blocks.append(f"- [{e.entity_type.value}] ({e.id}) {e.title}: {e.content}")
                    
                context_blocks.append("\n## Supporting Evidence Passages")
                for rent in retrieval_result.entities:
                    supplied_source_node_ids.add(rent.entity.id)
                    for ev in rent.evidence:
                        if ev.id:
                            supplied_evidence_ids.add(ev.id)
                    
                    for p in rent.passages:
                        context_blocks.append(f"Passage for {rent.entity.id}: {p.text}")
                        
                context_str = "\n".join(context_blocks)
    
                # 4. Prompt Construction
                system_instruction = (
                    "You are an expert educational presentation planner. "
                    "Your task is to generate a sequence of presentation slides based ONLY on the provided academic context. "
                    "You must output valid JSON matching the specified schema. "
                    "CRITICAL RULES: \n"
                    "1. NEVER invent source_node_ids or evidence_ids. You may only use IDs explicitly provided in the context.\n"
                    "2. Every factual slide MUST include at least one valid source_node_id.\n"
                    f"3. Include Examples: {str(include_examples).upper()}.\n"
                    f"4. Include Questions: {str(include_questions).upper()}.\n"
                    f"5. Audience Level: {audience_level}.\n"
                    f"6. Depth: {depth}.\n"
                    "7. Follow the academic hierarchy logically (e.g. Unit title, followed by Topics, then Concepts)."
                )
                
                prompt = f"Plan slides for the following academic content:\n\n{context_str}"
                
                llm_req = LLMGenerationRequest(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    temperature=0.0,
                    json_schema=SLIDE_FRAGMENT_SCHEMA
                )
                
                # 5. Generation
                llm_res = await self.llm_provider.generate(llm_req)
                
                # 6. Validation and Merging
                if not llm_res.structured_output or "slides" not in llm_res.structured_output:
                    raise GroundingValidationError(f"Invalid JSON or missing 'slides' array in chunk for Unit '{unit.title}'.")
                    
                for slide_dict in llm_res.structured_output["slides"]:
                    # Pydantic validation
                    try:
                        slide = SlideModel(**slide_dict)
                    except Exception as e:
                        raise GroundingValidationError(f"Malformed SlideModel structure: {str(e)}")
                        
                    # Strict Fabrication Check
                    for sid in slide.source_node_ids:
                        if sid not in supplied_source_node_ids:
                            raise GroundingValidationError(f"Fabricated source_node_id '{sid}' detected in slide '{slide.title}'.")
                            
                    for eid in slide.evidence_ids:
                        if eid not in supplied_evidence_ids:
                            raise GroundingValidationError(f"Fabricated evidence_id '{eid}' detected in slide '{slide.title}'.")
                            
                    # Config constraints
                    if not include_examples and slide.slide_type == SlideType.EXAMPLE:
                        raise GroundingValidationError(f"Generated EXAMPLE slide when include_examples is False.")
                        
                    if not include_questions and slide.slide_type == SlideType.QUESTION:
                        raise GroundingValidationError(f"Generated QUESTION slide when include_questions is False.")
                    
                    final_plan.slides.append(slide)

        return final_plan
