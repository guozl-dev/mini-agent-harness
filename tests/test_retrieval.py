"""Phase 4 tests: planned retrieval, plan parsing and fallbacks."""

from __future__ import annotations

import json

from mini_harness.core.retrieval import (
    Document,
    NaiveRetriever,
    PlannedRetriever,
    parse_plan,
)

DOCS = [
    Document(id="d2", text="状态持久化到 SQLite，进程崩溃后可以从快照断点续跑。"),
    Document(id="d4", text="工具用 allowlist 白名单限制，越权调用会被拒绝。"),
]


def test_naive_retriever_matches_on_literal_overlap() -> None:
    retriever = NaiveRetriever(DOCS)

    results = retriever.retrieve("断点续跑", k=2)

    assert [doc.id for doc in results][0] == "d2"


def test_naive_retriever_misses_paraphrased_question() -> None:
    retriever = NaiveRetriever(DOCS)

    assert retriever.retrieve("程序挂了还能继续吗", k=2) == []


def test_planned_retriever_recalls_paraphrased_question() -> None:
    plan = json.dumps({"sub_queries": ["崩溃后恢复"], "keywords": ["崩溃", "续跑"]})
    retriever = PlannedRetriever(DOCS, lambda _: plan)

    results = retriever.retrieve("程序挂了还能继续吗", k=2)

    assert "d2" in [doc.id for doc in results]


def test_keyword_bonus_can_surface_doc_without_similarity() -> None:
    plan = json.dumps({"sub_queries": ["zzz"], "keywords": ["allowlist"]})
    retriever = PlannedRetriever(DOCS, lambda _: plan)

    results = retriever.retrieve("完全无关的问题", k=2)

    assert [doc.id for doc in results] == ["d4"]


def test_parse_plan_handles_code_fences_and_bad_json() -> None:
    fenced = '```json\n{"sub_queries": ["a"], "keywords": ["k"]}\n```'
    fallback = parse_plan("not json", "原始问题")

    assert parse_plan(fenced, "q").sub_queries == ["a"]
    assert fallback.sub_queries == ["原始问题"]
    assert fallback.keywords == []


def test_planner_failure_falls_back_to_raw_query() -> None:
    def broken(_: str) -> str:
        raise RuntimeError("planner down")

    retriever = PlannedRetriever(DOCS, broken)

    results = retriever.retrieve("断点续跑", k=1)

    assert [doc.id for doc in results] == ["d2"]
