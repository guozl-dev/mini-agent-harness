"""Phase 3 tests: layered memory, consolidation idempotency and pollution guards."""

from __future__ import annotations

import json
import time

from mini_harness.core.loop import AgentLoop
from mini_harness.core.memory import MemoryStore
from mini_harness.core.state import StateStore
from mini_harness.llm.provider import FakeProvider


def test_add_and_recall_fact() -> None:
    memory = MemoryStore()
    memory.add_fact("用户偏好中文回答，并要求结论先行")

    facts = memory.recall("中文回答")

    assert len(facts) == 1
    assert "结论先行" in facts[0].text
    assert facts[0].hits == 1


def test_recall_returns_empty_when_nothing_matches() -> None:
    memory = MemoryStore()
    memory.add_fact("用户常驻武汉")

    assert memory.recall("量子计算") == []
    assert memory.context_block("量子计算") == ""


def test_duplicate_fact_is_not_stored_twice() -> None:
    memory = MemoryStore()
    first = memory.add_fact("用户偏好中文回答")
    second = memory.add_fact("用户偏好中文回答")

    assert first.id == second.id
    assert len(memory.list_facts()) == 1


def test_key_conflict_is_parked_as_pending_not_overwritten() -> None:
    memory = MemoryStore()
    original = memory.add_fact("用户常驻武汉", key="user.city")
    incoming = memory.add_fact("用户常驻北京", key="user.city")

    assert original.status == "active"
    assert incoming.status == "pending"
    active = memory.list_facts()
    assert [fact.text for fact in active] == ["用户常驻武汉"]
    assert [fact.text for fact in memory.pending_conflicts()] == ["用户常驻北京"]


def test_consolidation_is_idempotent() -> None:
    memory = MemoryStore()
    memory.add_episode("s1", "用户说：以后回答先给结论")
    memory.add_episode("s1", "用户提到：每周五要做测试报告")
    summarizer = lambda _: json.dumps(  # noqa: E731
        [{"text": "用户要求回答先给结论"}, {"text": "用户每周五产出测试报告"}]
    )

    first_run = memory.consolidate("s1", summarizer)
    second_run = memory.consolidate("s1", summarizer)

    assert first_run == 2
    assert second_run == 0
    assert len(memory.list_facts()) == 2


def test_consolidation_tolerates_bad_model_output() -> None:
    memory = MemoryStore()
    memory.add_episode("s1", "noise")

    written = memory.consolidate("s1", lambda _: "not json at all")

    assert written == 0
    assert memory.consolidate("s1", lambda _: "[]") == 0  # episodes already marked done


def test_forget_archives_stale_facts() -> None:
    memory = MemoryStore()
    memory.add_fact("很久没用的事实")
    future = time.time() + 40 * 86400

    archived = memory.forget(ttl_days=30, now=future)

    assert archived == 1
    assert memory.list_facts() == []


def test_forget_trims_active_set_to_cap() -> None:
    memory = MemoryStore()
    for index in range(3):
        memory.add_fact(f"事实 {index}")

    archived = memory.forget(max_facts=1, ttl_days=3650)

    assert archived == 2
    assert len(memory.list_facts()) == 1


def test_loop_injects_memory_and_records_episode() -> None:
    memory = MemoryStore()
    memory.add_fact("用户偏好中文回答，结论先行")
    provider = FakeProvider(["已按偏好回答"])
    loop = AgentLoop(provider, store=StateStore(), memory=memory)

    result = loop.run("帮我总结中文回答的偏好")

    first_call = provider.calls[0]
    assert any(message.content.startswith("[记忆]") for message in first_call)
    assert any("结论先行" in message.content for message in first_call)
    assert result.status == "finished"
    # Episode written for the finished run; consolidation then turns it into facts.
    written = memory.consolidate(
        result.run_id, lambda _: json.dumps([{"text": "用户偏好中文回答，结论先行"}])
    )
    assert written == 0  # identical to the existing fact, deduped
