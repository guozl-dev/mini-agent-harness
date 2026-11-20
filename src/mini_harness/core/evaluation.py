"""Retrieval evaluation: hit rate, MRR and a markdown table for the README."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from .retrieval import Document


@dataclass(frozen=True)
class EvalCase:
    question: str
    expected_ids: list[str]


class Retriever(Protocol):
    name: str

    def retrieve(self, query: str, k: int = 3) -> list[Document]: ...


def evaluate(retriever: Retriever, cases: Sequence[EvalCase], *, k: int = 3) -> dict[str, float]:
    hits = 0
    reciprocal_ranks = 0.0
    for case in cases:
        retrieved = [doc.id for doc in retriever.retrieve(case.question, k=k)]
        if any(doc_id in retrieved for doc_id in case.expected_ids):
            hits += 1
        for rank, doc_id in enumerate(retrieved, start=1):
            if doc_id in case.expected_ids:
                reciprocal_ranks += 1.0 / rank
                break
    total = max(len(cases), 1)
    return {
        "hit_rate": hits / total,
        "mrr": reciprocal_ranks / total,
        "cases": float(len(cases)),
    }


def markdown_table(results: dict[str, dict[str, float]]) -> str:
    lines = ["| Retriever | Hit@3 | MRR | Cases |", "|---|---|---|---|"]
    for name, metrics in results.items():
        lines.append(
            f"| {name} | {metrics['hit_rate']:.0%} | {metrics['mrr']:.2f} | "
            f"{int(metrics['cases'])} |"
        )
    return "\n".join(lines)
