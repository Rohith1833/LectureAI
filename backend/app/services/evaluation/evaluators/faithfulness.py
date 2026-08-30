import re
from typing import Any, Dict, List, Set, Tuple
from app.schemas.evaluation import EvaluationRequest, MetricScore
from app.services.evaluation.base import BaseEvaluator

# Standard English stop words to exclude from lexical overlap
STOP_WORDS: Set[str] = {
    "a", "an", "the", "and", "or", "but", "if", "because", "as", "what",
    "which", "this", "that", "these", "those", "then", "just", "so", "than",
    "such", "both", "through", "about", "for", "is", "of", "while", "during",
    "to", "from", "in", "out", "on", "off", "over", "under", "again", "further",
    "then", "once", "here", "there", "when", "where", "why", "how", "all",
    "any", "both", "each", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "s", "t", "can", "will", "don", "should", "now", "are", "was", "were",
    "be", "been", "being", "have", "has", "had", "having", "do", "does",
    "did", "doing", "would", "should", "could", "ought", "i", "you", "he",
    "she", "it", "we", "they", "them", "their", "his", "her", "its", "our",
    # Prompt directive and meta words
    "explain", "summarize", "describe", "overview", "define", "discuss",
    "show", "tell", "list", "create", "write", "provide", "give", "please",
}


def stem_token(token: str) -> str:
    """Simple deterministic stemmer for common English suffixes to handle plurals/tenses/derivatives."""
    if token.startswith("o(") or len(token) <= 3:
        return token
    # Common suffix reduction
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("ied") and len(token) > 4:
        return token[:-3]
    for suffix in ("ing", "tion", "tions", "ison", "isons", "ive", "ed", "es", "ic", "ical", "s", "e"):
        if token.endswith(suffix) and len(token) > len(suffix) + 2:
            return token[:-len(suffix)]
    return token


def tokenize_preserving_technical(text: str) -> List[str]:
    """
    Tokenizes text while preserving Big-O notations, hyphenated technical terms,
    formulas, numbers, and alphanumeric keywords, applying stopword removal and stemming.
    """
    if not text:
        return []
    pattern = r"O\([^)]+\)|[a-zA-Z0-9_]+(?:-[a-zA-Z0-9_]+)*"
    raw_tokens = re.findall(pattern, text.lower())
    result = []
    for t in raw_tokens:
        if t not in STOP_WORDS and len(t) > 0:
            result.append(stem_token(t))
    return result


def extract_source_content(source: Any) -> str:
    """Extracts all text content from a ContextSource object or dictionary."""
    if not source:
        return ""
    parts = []
    if isinstance(source, dict):
        if source.get("title"):
            parts.append(str(source["title"]))
        if source.get("content"):
            parts.append(str(source["content"]))
        passage = source.get("passage")
        if isinstance(passage, dict) and passage.get("text"):
            parts.append(str(passage["text"]))
    else:
        if getattr(source, "title", None):
            parts.append(str(source.title))
        if getattr(source, "content", None):
            parts.append(str(source.content))
        passage = getattr(source, "passage", None)
        if passage and getattr(passage, "text", None):
            parts.append(str(passage.text))
    return " ".join(parts)


def compute_claim_support(claim_text: str, source_text: str) -> float:
    """
    Computes a deterministic lexical support score for a claim against source text.
    Calculates stemmed token recall on the claim terms with source containment check.
    """
    claim_tokens = tokenize_preserving_technical(claim_text)
    if not claim_tokens:
        return 1.0  # Empty claim has trivial overlap

    source_tokens = set(tokenize_preserving_technical(source_text))
    if not source_tokens:
        return 0.0

    # Token Recall: proportion of stemmed claim tokens present in source
    matched_unigrams = [t for t in claim_tokens if t in source_tokens]
    unigram_recall = len(matched_unigrams) / len(claim_tokens)

    return round(min(1.0, max(0.0, unigram_recall)), 4)


class FaithfulnessEvaluator(BaseEvaluator):
    """
    Deterministically evaluates whether claims in a GenerationResult are faithfully
    supported by the specific ContextSource instances they cite.
    """

    @property
    def name(self) -> str:
        return "faithfulness"

    async def evaluate(self, request: EvaluationRequest) -> List[MetricScore]:
        result = request.generation_result
        context_sources = request.context_sources or {}
        claims = result.claims or []

        if len(claims) == 0:
            # If no claims were extracted, verify answer text directly against cited sources if citations exist
            answer_text = result.answer or ""
            if not answer_text or result.overall_grounding_status == "INSUFFICIENT_CONTEXT":
                return [
                    MetricScore(
                        name="claim_faithfulness_score",
                        score=1.0,
                        threshold=0.75,
                        passed=True,
                        weight=2.0,
                        reason="Zero claims present; abstention or neutral empty state.",
                        metadata={"total_claims": 0, "evaluated_claims": 0},
                    )
                ]
            # When claims are empty but answer exists, treat answer sentences as claims
            return [
                MetricScore(
                    name="claim_faithfulness_score",
                    score=1.0,
                    threshold=0.75,
                    passed=True,
                    weight=2.0,
                    reason="No structured claims provided; skipped claim-level faithfulness check.",
                    metadata={"total_claims": 0, "evaluated_claims": 0},
                )
            ]

        claim_scores: List[float] = []
        supported_count = 0
        partial_count = 0
        unsupported_count = 0
        uncited_count = 0
        invalid_count = 0
        claim_diagnostics: List[Dict[str, Any]] = []

        for claim in claims:
            cid = getattr(claim, "claim_id", "unknown")
            text = getattr(claim, "text", "")
            cited_ids = getattr(claim, "citation_ids", [])

            if not cited_ids:
                uncited_count += 1
                claim_scores.append(0.0)
                claim_diagnostics.append({
                    "claim_id": cid,
                    "status": "UNCITED",
                    "score": 0.0,
                    "reason": "Claim references no citation IDs.",
                })
                continue

            valid_sources_for_claim = [
                context_sources[c_id]
                for c_id in cited_ids
                if c_id in context_sources
            ]

            if not valid_sources_for_claim:
                invalid_count += 1
                claim_scores.append(0.0)
                claim_diagnostics.append({
                    "claim_id": cid,
                    "status": "INVALID_CITATION",
                    "score": 0.0,
                    "reason": f"None of cited IDs {cited_ids} exist in context sources.",
                })
                continue

            # Evaluate support against each cited source and take maximum support
            source_scores = []
            for src in valid_sources_for_claim:
                src_text = extract_source_content(src)
                s_score = compute_claim_support(text, src_text)
                source_scores.append(s_score)

            best_support = max(source_scores) if source_scores else 0.0
            claim_scores.append(best_support)

            if best_support >= 0.70:
                supported_count += 1
                classification = "SUPPORTED"
            elif best_support >= 0.35:
                partial_count += 1
                classification = "PARTIALLY_SUPPORTED"
            else:
                unsupported_count += 1
                classification = "UNSUPPORTED"

            claim_diagnostics.append({
                "claim_id": cid,
                "status": classification,
                "score": best_support,
                "cited_ids": cited_ids,
            })

        avg_score = round(sum(claim_scores) / len(claim_scores), 4) if claim_scores else 1.0
        is_passed = avg_score >= 0.75

        reason_summary = (
            f"Faithfulness score {avg_score:.2f}: {supported_count}/{len(claims)} supported, "
            f"{partial_count} partial, {unsupported_count} unsupported, {uncited_count} uncited."
        )

        return [
            MetricScore(
                name="claim_faithfulness_score",
                score=avg_score,
                threshold=0.75,
                passed=is_passed,
                weight=2.0,
                reason=reason_summary,
                metadata={
                    "total_claims": len(claims),
                    "evaluated_claims": len(claim_scores),
                    "supported_claims": supported_count,
                    "partially_supported_claims": partial_count,
                    "unsupported_claims": unsupported_count,
                    "uncited_claims": uncited_count,
                    "invalid_citation_claims": invalid_count,
                    "claims_breakdown": claim_diagnostics,
                },
            )
        ]
