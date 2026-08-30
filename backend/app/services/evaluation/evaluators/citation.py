import re
from typing import Any, Dict, List, Set
from app.schemas.evaluation import EvaluationRequest, MetricScore
from app.services.evaluation.base import BaseEvaluator


def extract_inline_citations(text: str) -> Set[str]:
    """Extracts all [S1], [S2] citation markers from text."""
    if not text:
        return set()
    return set(re.findall(r"\[(S\d+)\]", text))


def collect_all_cited_ids(result_dict: Dict[str, Any], claims: List[Any], citations_dict: Dict[str, Any], answer_text: str) -> Set[str]:
    """
    Recursively scans the GenerationResult to gather all cited citation IDs across
    claims, inline answer text, citation keys, and nested mode-specific structures.
    """
    cited: Set[str] = set()

    # 1. From top-level citations dict
    if citations_dict:
        cited.update(citations_dict.keys())

    # 2. From top-level claims
    for claim in claims:
        if hasattr(claim, "citation_ids"):
            cited.update(claim.citation_ids)
        elif isinstance(claim, dict) and "citation_ids" in claim:
            cited.update(claim["citation_ids"])

    # 3. From inline text in answer
    cited.update(extract_inline_citations(answer_text))

    # 4. From structured_output (Comparison / Study Guide)
    struct = result_dict.get("structured_output")
    if isinstance(struct, dict):
        # Comparison table
        for row in struct.get("comparison_table", []):
            if isinstance(row, dict):
                for val in row.get("values", []):
                    if isinstance(val, dict):
                        cited.update(val.get("citation_ids", []))
                        cited.update(extract_inline_citations(val.get("value", "")))

        # Comparison similarities & differences
        for item in struct.get("similarities", []):
            if isinstance(item, dict):
                cited.update(item.get("citation_ids", []))
                cited.update(extract_inline_citations(item.get("text", "")))
        for item in struct.get("differences", []):
            if isinstance(item, dict):
                cited.update(item.get("citation_ids", []))
                cited.update(extract_inline_citations(item.get("text", "")))

        # Study Guide key concepts & review questions
        for kc in struct.get("key_concepts", []):
            if isinstance(kc, dict):
                cited.update(kc.get("citation_ids", []))
                cited.update(extract_inline_citations(kc.get("definition", "")))
        for rq in struct.get("review_questions", []):
            if isinstance(rq, dict):
                cited.update(rq.get("citation_ids", []))
                cited.update(extract_inline_citations(rq.get("answer", "")))
                cited.update(extract_inline_citations(rq.get("explanation", "")))

    return {c.strip() for c in cited if isinstance(c, str) and c.strip()}


class CitationEvaluator(BaseEvaluator):
    """
    Deterministically evaluates citation validity rate, claim citation coverage,
    and context source utilization without mutating the GenerationResult.
    """

    @property
    def name(self) -> str:
        return "citation"

    async def evaluate(self, request: EvaluationRequest) -> List[MetricScore]:
        result = request.generation_result
        context_sources = request.context_sources or {}
        valid_context_ids: Set[str] = set(context_sources.keys())

        # Collect all referenced citation IDs
        result_dict = result.model_dump()
        all_cited_ids = collect_all_cited_ids(
            result_dict=result_dict,
            claims=result.claims,
            citations_dict=result.citations,
            answer_text=result.answer or "",
        )

        valid_cited_ids = all_cited_ids.intersection(valid_context_ids)
        invalid_cited_ids = all_cited_ids.difference(valid_context_ids)

        # 1. Citation Validity Rate
        if len(all_cited_ids) == 0:
            if len(valid_context_ids) == 0:
                validity_rate = 1.0
                validity_reason = "No citations expected for empty context."
            elif len(result.claims) > 0:
                validity_rate = 0.0
                validity_reason = "Claims present but zero citations provided."
            else:
                validity_rate = 1.0
                validity_reason = "Zero citations referenced."
        else:
            validity_rate = round(len(valid_cited_ids) / len(all_cited_ids), 4)
            if len(invalid_cited_ids) > 0:
                validity_reason = f"Invalid citation IDs detected: {sorted(list(invalid_cited_ids))}"
            else:
                validity_reason = f"All {len(valid_cited_ids)} cited sources are verified in context."

        validity_metric = MetricScore(
            name="citation_validity_rate",
            score=validity_rate,
            threshold=1.0,
            passed=validity_rate >= 1.0,
            weight=2.0,
            reason=validity_reason,
            metadata={
                "total_cited_ids": len(all_cited_ids),
                "valid_cited_ids": len(valid_cited_ids),
                "invalid_cited_ids": list(invalid_cited_ids),
            },
        )

        # 2. Claim Citation Coverage
        claims = result.claims or []
        if len(claims) == 0:
            claim_coverage = 1.0
            coverage_reason = "No claims present to evaluate coverage."
        else:
            claims_with_valid_citation = 0
            for c in claims:
                c_ids = set(c.citation_ids if hasattr(c, "citation_ids") else c.get("citation_ids", []))
                if any(cid in valid_context_ids for cid in c_ids):
                    claims_with_valid_citation += 1

            claim_coverage = round(claims_with_valid_citation / len(claims), 4)
            coverage_reason = (
                f"{claims_with_valid_citation}/{len(claims)} claims have verified citations."
            )

        coverage_metric = MetricScore(
            name="claim_citation_coverage",
            score=claim_coverage,
            threshold=0.80,
            passed=claim_coverage >= 0.80,
            weight=1.5,
            reason=coverage_reason,
            metadata={
                "total_claims": len(claims),
                "supported_claims_count": claims_with_valid_citation if len(claims) > 0 else 0,
            },
        )

        # 3. Context Utilization Rate
        if len(valid_context_ids) == 0:
            utilization_rate = 1.0
        else:
            used_ids = valid_context_ids.intersection(all_cited_ids)
            utilization_rate = round(len(used_ids) / len(valid_context_ids), 4)

        utilization_metric = MetricScore(
            name="context_utilization_rate",
            score=utilization_rate,
            threshold=0.0,
            passed=True,  # Informational diagnostic metric
            weight=0.5,
            reason=f"{len(valid_cited_ids)}/{len(valid_context_ids)} supplied context sources were referenced in output.",
            metadata={
                "total_context_sources": len(valid_context_ids),
                "used_context_sources": len(valid_cited_ids),
                "unused_context_ids": list(valid_context_ids.difference(all_cited_ids)),
            },
        )

        return [validity_metric, coverage_metric, utilization_metric]
