"""Retrieval strategies: naive top-k baseline vs planning-based recall.

The planned retriever asks a planner (an LLM in production, a dict in demos) for
sub-queries and keywords, retrieves each sub-query independently, then merges and
reranks — which is exactly what a single-shot vector top-k cannot do on
multi-hop or paraphrased questions.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .textutil import similarity

Planner = Callable[[str], str]


@dataclass(frozen=True)
class Document:
    id: str
    text: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class RetrievalPlan:
    sub_queries: list[str]
    keywords: list[str]


def parse_plan(raw: str, fallback_query: str) -> RetrievalPlan:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text.split("\n", 1)[1] if "\n" in text else text
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return RetrievalPlan([fallback_query], [])
    if not isinstance(payload, dict):
        return RetrievalPlan([fallback_query], [])
    sub_queries = [q for q in payload.get("sub_queries", []) if isinstance(q, str) and q.strip()]
    keywords = [k for k in payload.get("keywords", []) if isinstance(k, str) and k.strip()]
    return RetrievalPlan(sub_queries or [fallback_query], keywords)


class NaiveRetriever:
    """Baseline: single-shot similarity top-k."""

    name = "naive-topk"

    def __init__(self, documents: Sequence[Document]) -> None:
        self.documents = list(documents)

    def score(self, query: str, document: Document) -> float:
        return similarity(query, document.text)

    def retrieve(self, query: str, k: int = 3) -> list[Document]:
        ranked = sorted(
            ((self.score(query, doc), doc) for doc in self.documents),
            key=lambda item: item[0],
            reverse=True,
        )
        return [doc for score, doc in ranked[:k] if score > 0]


class PlannedRetriever:
    """Planning-based recall: sub-queries + keyword bonus + merge & rerank."""

    name = "planned"

    def __init__(
        self,
        documents: Sequence[Document],
        planner: Planner,
        *,
        keyword_bonus: float = 0.15,
        keyword_cap: float = 0.3,
    ) -> None:
        self.documents = list(documents)
        self.planner = planner
        self.keyword_bonus = keyword_bonus
        self.keyword_cap = keyword_cap

    def plan(self, query: str) -> RetrievalPlan:
        try:
            raw = self.planner(query)
        except Exception:  # noqa: BLE001 - planner failures fall back to the raw query
            return RetrievalPlan([query], [])
        return parse_plan(raw, query)

    def retrieve(self, query: str, k: int = 3) -> list[Document]:
        plan = self.plan(query)
        best: dict[str, float] = {}
        by_id = {doc.id: doc for doc in self.documents}
        for sub_query in plan.sub_queries[:3]:
            for doc in self.documents:
                score = similarity(sub_query, doc.text)
                if score > best.get(doc.id, 0.0):
                    best[doc.id] = score
        for doc in self.documents:
            if any(keyword in doc.text for keyword in plan.keywords):
                best.setdefault(doc.id, 0.0)
        for doc_id, score in list(best.items()):
            text = by_id[doc_id].text
            hits = sum(1 for keyword in plan.keywords if keyword in text)
            bonus = min(hits * self.keyword_bonus, self.keyword_cap)
            best[doc_id] = score + bonus
        ranked = sorted(best.items(), key=lambda item: item[1], reverse=True)
        return [by_id[doc_id] for doc_id, score in ranked[:k] if score > 0]

    @staticmethod
    def json_planner(provider: Any) -> Planner:
        """Adapt an ``LLMProvider`` into a planner callable."""

        def _planner(query: str) -> str:
            from ..llm.types import Message

            messages = [
                Message(
                    role="system",
                    content=(
                        "You are a retrieval planner. Return ONLY JSON: "
                        '{"sub_queries": ["..."], "keywords": ["..."]}. '
                        "Split multi-hop questions and add synonyms as keywords."
                    ),
                ),
                Message(role="user", content=query),
            ]
            return provider.complete(messages).content

        return _planner
