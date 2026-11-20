"""Phase 4 tests: hit rate, MRR and markdown reporting."""

from __future__ import annotations

from mini_harness.core.evaluation import EvalCase, evaluate, markdown_table
from mini_harness.core.retrieval import Document


class FakeRetriever:
    name = "fake"

    def __init__(self, mapping: dict[str, list[str]]) -> None:
        self.mapping = mapping

    def retrieve(self, query: str, k: int = 3) -> list[Document]:
        return [Document(id=doc_id, text="") for doc_id in self.mapping.get(query, [])][:k]


def test_evaluate_computes_hit_rate_and_mrr() -> None:
    retriever = FakeRetriever({"q1": ["a", "b"], "q2": ["x", "a"], "q3": ["z"]})
    cases = [
        EvalCase(question="q1", expected_ids=["a"]),
        EvalCase(question="q2", expected_ids=["a"]),
        EvalCase(question="q3", expected_ids=["missing"]),
    ]

    metrics = evaluate(retriever, cases, k=3)

    assert metrics["hit_rate"] == 2 / 3
    assert metrics["mrr"] == (1 / 1 + 1 / 2 + 0) / 3
    assert metrics["cases"] == 3


def test_markdown_table_contains_all_rows() -> None:
    table = markdown_table(
        {
            "naive": {"hit_rate": 0.14, "mrr": 0.14, "cases": 7},
            "planned": {"hit_rate": 1.0, "mrr": 0.93, "cases": 7},
        }
    )

    assert "| Retriever | Hit@3 | MRR | Cases |" in table
    assert "| naive | 14% | 0.14 | 7 |" in table
    assert "| planned | 100% | 0.93 | 7 |" in table
