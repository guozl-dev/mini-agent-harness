"""Shared text utilities: bigram sets and Jaccard similarity.

Used by memory recall and by both retrievers, so scoring stays consistent.
"""

from __future__ import annotations

import re


def bigrams(text: str) -> set[str]:
    cleaned = re.sub(r"[\s\W_]+", "", text.lower())
    return {cleaned[i : i + 2] for i in range(len(cleaned) - 1)} or {cleaned}


def similarity(left: str, right: str) -> float:
    a, b = bigrams(left), bigrams(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
