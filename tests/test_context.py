"""Phase 1 tests: context budget ladder (externalize -> summarize -> hard trim)."""

from __future__ import annotations

from mini_harness.core.context import ContextManager, estimate_tokens
from mini_harness.llm.types import Message


def test_estimate_tokens_is_monotonic() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("a" * 30) > estimate_tokens("a" * 3)


def test_short_conversation_passes_through_untouched() -> None:
    manager = ContextManager(budget_tokens=500)
    messages = [Message(role="system", content="s"), Message(role="user", content="hello")]

    assembled = manager.assemble(messages)

    assert [m.content for m in assembled] == ["s", "hello"]
    assert manager.trim_events == []


def test_oversized_tool_result_is_externalized() -> None:
    manager = ContextManager(budget_tokens=10000, externalize_over_chars=50)
    big = "x" * 400
    messages = [
        Message(role="system", content="s"),
        Message(role="user", content="run tests"),
        Message(role="tool", content=big, name="pytest", tool_call_id="c1"),
    ]

    assembled = manager.assemble(messages)

    assert assembled[2].content.startswith("[tool result externalized: 400 chars]")
    assert manager.externalized[2] == big
    assert any("externalized" in event for event in manager.trim_events)


def test_middle_turns_collapse_into_summary() -> None:
    manager = ContextManager(
        budget_tokens=200,
        keep_recent=2,
        summarizer=lambda text: "SUM",
    )
    messages = [Message(role="system", content="system")]
    messages += [Message(role="user", content=f"turn {i} " + "y" * 80) for i in range(6)]

    assembled = manager.assemble(messages)

    assert manager.last_summary == "SUM"
    assert any(m.content.startswith("[历史摘要] SUM") for m in assembled)
    assert len(assembled) < len(messages)
    assert assembled[-1].content.startswith("turn 5")


def test_hard_trim_keeps_system_and_drops_oldest() -> None:
    manager = ContextManager(budget_tokens=120, keep_recent=4)
    messages = [Message(role="system", content="keep me")]
    messages += [Message(role="user", content="z" * 200) for _ in range(6)]

    assembled = manager.assemble(messages)

    assert assembled[0].content == "keep me"
    assert any("hard-trimmed" in event for event in manager.trim_events)
    assert len(assembled) < len(messages)
