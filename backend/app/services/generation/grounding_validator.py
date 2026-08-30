"""
GroundingValidator — Phase 8E-3C

Pure deterministic transformation: validates citation IDs in model output
against the GenerationContext, strips invalid references, assigns per-claim
GroundingStatus, rolls up an overall status, and packages a GenerationResult.

Supports QA, EXPLANATION, SUMMARY, COMPARISON, and STUDY_GUIDE modes,
validating nested structures recursively.
"""

from loguru import logger
from typing import Any, Dict, List, Set

from app.schemas.generation import (
    ContextSource,
    GenerationClaim,
    GenerationContext,
    GenerationRequest,
    GenerationResult,
    GroundingStatus,
)
from app.services.generation.base import LLMGenerationResponse
from app.services.generation.errors import GroundingValidationError
from app.services.generation.modes.registry import strategy_registry


class GroundingValidator:
    """
    Validates LLM-generated structured output against the GenerationContext
    that was actually supplied to the model, producing a GenerationResult.
    """

    INSUFFICIENT_CONTEXT_MARKER = "INSUFFICIENT_CONTEXT"

    def validate(
        self,
        response: LLMGenerationResponse,
        context: GenerationContext,
        request: GenerationRequest,
    ) -> GenerationResult:
        """
        Transform an LLMGenerationResponse into a validated GenerationResult.

        Raises:
            GroundingValidationError: when structured_output is None, required
                schema fields are absent/wrong-type, or output cannot be parsed.
        """
        # ------------------------------------------------------------------ #
        # 1. Guard: structured output must be present                         #
        # ------------------------------------------------------------------ #
        if response.structured_output is None:
            raise GroundingValidationError(
                "Model returned no structured output. Expected a JSON object."
            )

        raw: Dict[str, Any] = response.structured_output

        # ------------------------------------------------------------------ #
        # 2. Resolve Strategy and Validate Schema Structure                  #
        # ------------------------------------------------------------------ #
        try:
            strategy = strategy_registry.get(request.mode)
        except Exception as e:
            raise GroundingValidationError(
                f"Unsupported generation mode strategy: '{request.mode}'."
            ) from e

        schema = strategy.json_schema
        required_keys = schema.get("required", [])
        for key in required_keys:
            if key not in raw:
                raise GroundingValidationError(
                    f"Structured output is missing required field: '{key}'."
                )

        # Validate types of keys present in structured output
        properties = schema.get("properties", {})
        for key, prop in properties.items():
            if key in raw:
                # 'claims' field is handled/warned gracefully in validate_claims_citations if not a list
                if key == "claims":
                    continue
                val = raw[key]
                expected_type = prop.get("type")
                if expected_type == "array" and not isinstance(val, list):
                    raise GroundingValidationError(
                        f"Field '{key}' must be an array/list; got {type(val).__name__}."
                    )
                elif expected_type == "string" and not isinstance(val, str):
                    raise GroundingValidationError(
                        f"Field '{key}' must be a string; got {type(val).__name__}."
                    )
                elif expected_type == "object" and not isinstance(val, dict):
                    raise GroundingValidationError(
                        f"Field '{key}' must be an object/dict; got {type(val).__name__}."
                    )

        # ------------------------------------------------------------------ #
        # 3. Extract grounded answer text (fallback to title if answer missing)#
        # ------------------------------------------------------------------ #
        answer = raw.get("answer")
        if answer is None:
            answer = raw.get("title")

        if answer is None:
            raise GroundingValidationError(
                "Structured output must contain an 'answer' or 'title' field."
            )
        if not isinstance(answer, str):
            raise GroundingValidationError(
                f"Grounded text field must be a string; got {type(answer).__name__}."
            )

        # ------------------------------------------------------------------ #
        # 4. Recursive Nested Citation Validation                            #
        # ------------------------------------------------------------------ #
        valid_ids: Set[str] = {source.citation_id for source in context.sources}
        invalid_citations: List[str] = []
        valid_citations_tracker: Set[str] = set()

        sanitized_output = self._validate_citations_recursively(
            raw, valid_ids, invalid_citations, valid_citations_tracker
        )

        # ------------------------------------------------------------------ #
        # 5. Process top-level claims if they exist                          #
        # ------------------------------------------------------------------ #
        raw_claims = sanitized_output.get("claims", [])
        validated_claims = self.validate_claims_citations(raw_claims, context)

        # ------------------------------------------------------------------ #
        # 6. Detect INSUFFICIENT_CONTEXT marker (scans recursively)          #
        # ------------------------------------------------------------------ #
        insufficient = self._has_insufficient_context(sanitized_output)

        # ------------------------------------------------------------------ #
        # 7. Grounding status rollup                                         #
        # ------------------------------------------------------------------ #
        overall = self._rollup_status(
            validated_claims,
            insufficient,
            has_invalid_citations=len(invalid_citations) > 0,
            has_valid_citations=len(valid_citations_tracker) > 0,
        )

        # ------------------------------------------------------------------ #
        # 8. Build citations dict — includes all referenced valid citation IDs#
        # ------------------------------------------------------------------ #
        referenced_ids: Set[str] = set()
        for claim in validated_claims:
            referenced_ids.update(claim.citation_ids)
        referenced_ids.update(valid_citations_tracker)

        citations: Dict[str, ContextSource] = {
            source.citation_id: source
            for source in context.sources
            if source.citation_id in referenced_ids
        }

        # ------------------------------------------------------------------ #
        # 9. Populate model_metadata from provider response                  #
        # ------------------------------------------------------------------ #
        model_metadata: Dict[str, Any] = {
            "model_name": response.model_name,
        }
        if response.token_usage:
            model_metadata["token_usage"] = response.token_usage

        # ------------------------------------------------------------------ #
        # 10. Return GenerationResult                                        #
        # ------------------------------------------------------------------ #
        return GenerationResult(
            mode=request.mode,
            answer=answer,
            structured_output=sanitized_output,
            claims=validated_claims,
            citations=citations,
            overall_grounding_status=overall,
            model_metadata=model_metadata,
        )

    # ---------------------------------------------------------------------- #
    # Public & Private helpers                                                 #
    # ---------------------------------------------------------------------- #

    def validate_claims_citations(
        self,
        raw_claims: Any,
        context: GenerationContext,
    ) -> List[GenerationClaim]:
        """
        Pure reusable validation logic that takes a raw claims list and context,
        resolves citation IDs, strips invalid ones, logs warnings, and returns
        a list of GenerationClaim schemas with their grounding status set.
        """
        valid_ids: Set[str] = {source.citation_id for source in context.sources}
        validated_claims: List[GenerationClaim] = []

        if not isinstance(raw_claims, list):
            return validated_claims

        for idx, raw_claim in enumerate(raw_claims):
            if not isinstance(raw_claim, dict):
                logger.warning(
                    "GroundingValidator: claim[{}] is not a dict; skipping.",
                    idx,
                )
                continue

            claim_id = str(raw_claim.get("claim_id", f"c{idx + 1}"))
            text = raw_claim.get("text", "")
            if not isinstance(text, str):
                text = str(text)

            raw_citation_ids = raw_claim.get("citation_ids", [])
            if not isinstance(raw_citation_ids, list):
                raw_citation_ids = []

            # Partition into valid and invalid
            surviving: List[str] = []
            invalid: List[str] = []
            for cid in raw_citation_ids:
                if isinstance(cid, str) and cid in valid_ids:
                    surviving.append(cid)
                else:
                    invalid.append(str(cid))

            if invalid:
                logger.warning(
                    "GroundingValidator: claim '{}' referenced invalid citation "
                    "IDs {} (not in context); stripped from result.",
                    claim_id,
                    invalid,
                )

            # Assign per-claim grounding status
            if not raw_citation_ids:
                status = GroundingStatus.UNSUPPORTED
            elif surviving and len(surviving) == len(raw_citation_ids):
                status = GroundingStatus.SUPPORTED
            elif surviving:
                status = GroundingStatus.PARTIALLY_SUPPORTED
            else:
                status = GroundingStatus.UNSUPPORTED

            validated_claims.append(
                GenerationClaim(
                    claim_id=claim_id,
                    text=text,
                    citation_ids=surviving,
                    grounding_status=status,
                )
            )

        return validated_claims

    def _validate_citations_recursively(
        self,
        data: Any,
        valid_ids: Set[str],
        invalid_citations: List[str],
        valid_citations: Set[str],
    ) -> Any:
        """
        Recursively scans and sanitizes citation lists inside nested dicts/lists.
        """
        if isinstance(data, dict):
            new_dict = {}
            for k, v in data.items():
                if k == "claims":
                    # Let validate_claims_citations handle the claims list
                    new_dict[k] = v
                elif k == "citation_ids" and isinstance(v, list):
                    sanitized_list = []
                    for cid in v:
                        if isinstance(cid, str) and cid in valid_ids:
                            sanitized_list.append(cid)
                            valid_citations.add(cid)
                        else:
                            invalid_citations.append(str(cid))
                            logger.warning(
                                "GroundingValidator: stripped invalid nested "
                                "citation ID '{}' from field '{}'.",
                                cid,
                                k,
                            )
                    new_dict[k] = sanitized_list
                else:
                    new_dict[k] = self._validate_citations_recursively(
                        v, valid_ids, invalid_citations, valid_citations
                    )
            return new_dict
        elif isinstance(data, list):
            return [
                self._validate_citations_recursively(
                    item, valid_ids, invalid_citations, valid_citations
                )
                for item in data
            ]
        return data

    def _has_insufficient_context(self, data: Any) -> bool:
        """Recursively checks if the INSUFFICIENT_CONTEXT marker is in any text."""
        if isinstance(data, str):
            return self.INSUFFICIENT_CONTEXT_MARKER in data
        elif isinstance(data, dict):
            return any(self._has_insufficient_context(v) for v in data.values())
        elif isinstance(data, list):
            return any(self._has_insufficient_context(item) for item in data)
        return False

    def _rollup_status(
        self,
        claims: List[GenerationClaim],
        insufficient: bool,
        has_invalid_citations: bool,
        has_valid_citations: bool,
    ) -> GroundingStatus:
        """Deterministic overall status rollup from per-claim and nested statuses."""
        if insufficient:
            return GroundingStatus.INSUFFICIENT_CONTEXT

        # If claims are present, roll up based on claims
        if claims:
            statuses = {c.grounding_status for c in claims}
            if has_invalid_citations:
                return GroundingStatus.PARTIALLY_SUPPORTED
            if statuses == {GroundingStatus.SUPPORTED}:
                return GroundingStatus.SUPPORTED
            return GroundingStatus.PARTIALLY_SUPPORTED

        # If no claims (e.g. Comparison mode), roll up based on nested citations directly
        if not has_valid_citations and not has_invalid_citations:
            return GroundingStatus.UNSUPPORTED

        if has_invalid_citations:
            if has_valid_citations:
                return GroundingStatus.PARTIALLY_SUPPORTED
            else:
                return GroundingStatus.UNSUPPORTED

        return GroundingStatus.SUPPORTED
