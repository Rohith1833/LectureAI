import re
from dataclasses import dataclass
from typing import List


@dataclass
class NormalizedQuery:
    raw: str
    normalized: str
    terms: List[str]


class QueryNormalizer:
    """
    Handles deterministic normalization and tokenization of search queries.
    Splits text into cleaned, deduplicated lowercase terms while maintaining input order.
    """

    def normalize(self, query: str) -> NormalizedQuery:
        """
        Transforms raw query string to a NormalizedQuery.
        Pipeline: strip -> lowercase -> split on non-alphanumeric -> remove empty -> deduplicate.
        """
        raw_query = query
        stripped = query.strip()
        normalized_str = stripped.lower()

        # Tokenize by splitting on any non-alphanumeric character sequence
        raw_tokens = re.split(r'[^a-zA-Z0-9]+', normalized_str)
        tokens = [t for t in raw_tokens if t]

        # Deduplicate terms while preserving original insertion order
        unique_terms = list(dict.fromkeys(tokens))

        return NormalizedQuery(
            raw=raw_query,
            normalized=normalized_str,
            terms=unique_terms
        )
