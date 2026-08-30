"""
GenerationService — Phase 8D & Phase 8G-2

Orchestrates the complete grounded generation pipeline:

  GenerationRequest (with optional conversation_id)
        ↓
  Resolve & Validate Conversation Scope (Phase 8G-2)
        ↓
  Retrieve Bounded Conversation History (Phase 8G-2)
        ↓
  convert → RetrievalRequest
        ↓
  RetrievalService.retrieve()            [Phase 7, sync]
        ↓
  RetrievalResult
        ↓
  ContextBuilder.build()                 [Phase 8B]
        ↓
  GenerationContext (attaching conversation history separately)
        ↓
  PromptBuilder.build()                  [Phase 8B & 8G-2]
        ↓
  LLMGenerationRequest
        ↓
  await LLMProvider.generate()           [Phase 8C, async]
        ↓
  LLMGenerationResponse
        ↓
  GroundingValidator.validate()          [Phase 8D]
        ↓
  GenerationResult
        ↓
  Persist USER & ASSISTANT messages      [Phase 8G-2]

CRITICAL ARCHITECTURAL RULES:
1. The service MUST NOT directly query KnowledgeRepository, AcademicGraph,
   KnowledgeVersion, OCR results, or any domain data outside of what Phase 7
   retrieval provides. The sole knowledge path is Phase 7 → RetrievalResult.
2. Conversation history is supplementary context. It NEVER replaces Phase 7
   retrieval and is NEVER treated as a citation source.
"""

from typing import List, Optional
from loguru import logger

from app.schemas.generation import (
    ConversationTurn,
    GenerationContext,
    GenerationRequest,
    GenerationResult,
)
from app.schemas.retrieval import RetrievalRequest
from app.services.generation.base import LLMProvider
from app.services.generation.context_builder import ContextBuilder
from app.services.generation.grounding_validator import GroundingValidator
from app.services.generation.prompt_builder import PromptBuilder
from app.services.retrieval.retrieval_service import RetrievalService
from app.repositories.conversation_repository import (
    ConversationRepository,
    MessageRepository,
)


class GenerationService:
    """
    Orchestrates the end-to-end grounded generation pipeline.

    All dependencies are injected to enable unit-testing without live
    infrastructure. Only the LLM provider call is awaited asynchronously;
    Phase 7 retrieval is synchronous and called normally.
    """

    def __init__(
        self,
        retrieval_service: RetrievalService,
        provider: LLMProvider,
        context_builder: Optional[ContextBuilder] = None,
        prompt_builder: Optional[PromptBuilder] = None,
        grounding_validator: Optional[GroundingValidator] = None,
        conversation_repo: Optional[ConversationRepository] = None,
        message_repo: Optional[MessageRepository] = None,
        history_limit: int = 10,
        history_max_chars: int = 8000,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.provider = provider
        self.context_builder = context_builder or ContextBuilder()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.grounding_validator = grounding_validator or GroundingValidator()
        self.conversation_repo = conversation_repo
        self.message_repo = message_repo
        self.history_limit = history_limit
        self.history_max_chars = history_max_chars

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """
        Execute the complete grounded generation pipeline asynchronously.

        Phase 7 retrieval is synchronous and called normally.
        The LLM provider call is awaited.

        Raises:
            ValueError: propagated from conversation validation or RetrievalService.
            LLMProviderError: propagated from the provider adapter.
            GroundingValidationError: propagated from GroundingValidator.
        """
        logger.info(
            "GenerationService.generate: query='{}' document_id='{}' conversation_id='{}'",
            request.query[:80],
            request.scope.document_id,
            request.conversation_id,
        )

        conversation_turns: List[ConversationTurn] = []

        # ------------------------------------------------------------------ #
        # Step 1: Resolve & Validate Conversation Scope if provided (8G-2)    #
        # ------------------------------------------------------------------ #
        if request.conversation_id is not None:
            if self.conversation_repo is None or self.message_repo is None:
                raise ValueError("Conversation repositories are not configured on GenerationService.")

            conv = self.conversation_repo.get_conversation(request.conversation_id)
            if not conv:
                raise ValueError(f"Conversation with ID '{request.conversation_id}' does not exist.")

            if conv.document_id != request.scope.document_id:
                raise ValueError(
                    f"Conversation '{request.conversation_id}' does not belong to Document '{request.scope.document_id}'."
                )

            if conv.status == "ARCHIVED":
                raise ValueError(
                    f"Cannot generate in ARCHIVED conversation '{request.conversation_id}'."
                )

            # Knowledge version scope compatibility
            if conv.knowledge_version_id is not None:
                if request.scope.version_id is not None and request.scope.version_id != conv.knowledge_version_id:
                    raise ValueError(
                        f"Conversation is pinned to KnowledgeVersion '{conv.knowledge_version_id}', "
                        f"but request specified version '{request.scope.version_id}'."
                    )
                elif request.scope.version_id is None:
                    request.scope.version_id = conv.knowledge_version_id

            # Retrieve bounded conversation history
            db_messages = self.message_repo.list_messages(request.conversation_id)
            if db_messages:
                # Bounded slice: latest complete turns
                sliced = db_messages[-self.history_limit :] if len(db_messages) > self.history_limit else db_messages

                # Enforce total character budget over turns from newest to oldest
                budget_turns = []
                accumulated_chars = 0
                for msg in reversed(sliced):
                    msg_len = len(msg.content or "")
                    if accumulated_chars + msg_len > self.history_max_chars and budget_turns:
                        break
                    budget_turns.append(msg)
                    accumulated_chars += msg_len

                # Restore chronological sequence order
                budget_turns.reverse()

                conversation_turns = [
                    ConversationTurn(role=m.role, content=m.content, sequence=m.sequence)
                    for m in budget_turns
                ]

        elif request.conversation_context:
            for item in request.conversation_context:
                role = item.get("role", "USER")
                content = item.get("content", "")
                if content:
                    conversation_turns.append(ConversationTurn(role=role, content=content))

        # ------------------------------------------------------------------ #
        # Step 2: Convert GenerationRequest → RetrievalRequest                #
        # ------------------------------------------------------------------ #
        retrieval_request = RetrievalRequest(
            query=request.query,
            scope=request.scope,
            options=request.retrieval_options,
        )

        # ------------------------------------------------------------------ #
        # Step 3: Phase 7 retrieval (synchronous — do NOT make it async)      #
        # ------------------------------------------------------------------ #
        retrieval_result = self.retrieval_service.retrieve(retrieval_request)
        logger.debug(
            "GenerationService: retrieval returned {} entities",
            len(retrieval_result.entities),
        )

        # ------------------------------------------------------------------ #
        # Step 4: Build grounding context (Phase 8B & 8G-2)                   #
        # ------------------------------------------------------------------ #
        context: GenerationContext = self.context_builder.build(retrieval_result)
        context.conversation_history = conversation_turns
        logger.debug(
            "GenerationService: context contains {} sources and {} history turns",
            len(context.sources),
            len(context.conversation_history),
        )

        # ------------------------------------------------------------------ #
        # Step 5: Build LLM prompt (Phase 8B & 8G-2)                          #
        # ------------------------------------------------------------------ #
        llm_request = self.prompt_builder.build(request, context)

        # ------------------------------------------------------------------ #
        # Step 6: Call provider asynchronously (Phase 8C)                     #
        # ------------------------------------------------------------------ #
        llm_response = await self.provider.generate(llm_request)
        logger.debug(
            "GenerationService: provider responded (model='{}')",
            llm_response.model_name,
        )

        # ------------------------------------------------------------------ #
        # Step 7: Validate grounding and build GenerationResult (Phase 8D)   #
        # ------------------------------------------------------------------ #
        result = self.grounding_validator.validate(llm_response, context, request)
        logger.info(
            "GenerationService: grounding_status='{}' claims={}",
            result.overall_grounding_status,
            len(result.claims),
        )

        # ------------------------------------------------------------------ #
        # Step 8: Persist USER & ASSISTANT messages on success (8G-2)         #
        # ------------------------------------------------------------------ #
        if request.conversation_id is not None and self.message_repo is not None:
            # 1. Persist USER message
            self.message_repo.append_message(
                conversation_id=request.conversation_id,
                role="USER",
                content=request.query,
            )
            # 2. Persist ASSISTANT message
            self.message_repo.append_message(
                conversation_id=request.conversation_id,
                role="ASSISTANT",
                content=result.answer,
            )
            logger.debug(
                "GenerationService: persisted USER and ASSISTANT messages to conversation '{}'",
                request.conversation_id,
            )

        return result
