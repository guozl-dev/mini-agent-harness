"""Phase 1 tests: tool allowlist, timeout, guard and error-to-observation."""

from __future__ import annotations

import time

import pytest

from mini_harness.core.tools import ToolRegistry
from mini_harness.llm.types import ToolCall, ToolSpec


def _spec(name: str = "echo") -> ToolSpec:
    return ToolSpec(name=name, description="echo text", parameters={"type": "object"})


def test_registered_tool_returns_output() -> None:
    registry = ToolRegistry()
    registry.register(_spec(), lambda text: text.upper())

    observation = registry.execute(ToolCall(id="c1", name="echo", arguments={"text": "hi"}))

    assert observation.ok is True
    assert observation.output == "HI"
    assert observation.duration_ms >= 0


def test_allowlist_blocks_tool_and_hides_it_from_specs() -> None:
    registry = ToolRegistry()
    registry.register(_spec("danger"), lambda: "nope", allowed=False)

    observation = registry.execute(ToolCall(id="c1", name="danger"))

    assert observation.ok is False
    assert observation.error == "tool_not_allowed"
    assert registry.specs() == []
    assert [s.name for s in registry.specs(only_allowed=False)] == ["danger"]


def test_unknown_tool_is_reported_not_raised() -> None:
    registry = ToolRegistry()

    observation = registry.execute(ToolCall(id="c1", name="ghost"))

    assert observation.ok is False
    assert observation.error == "tool_not_found"


def test_timeout_becomes_observation() -> None:
    registry = ToolRegistry(timeout_s=0.05)
    registry.register(_spec("slow"), lambda: time.sleep(0.3) or "late")

    observation = registry.execute(ToolCall(id="c1", name="slow"))

    assert observation.ok is False
    assert observation.error.startswith("timeout after")


def test_exception_becomes_observation() -> None:
    def boom() -> str:
        raise ValueError("kaboom")

    registry = ToolRegistry()
    registry.register(_spec("boom"), boom)

    observation = registry.execute(ToolCall(id="c1", name="boom"))

    assert observation.ok is False
    assert observation.error == "ValueError: kaboom"


def test_bad_arguments_are_reported() -> None:
    registry = ToolRegistry()
    registry.register(_spec(), lambda text: text)

    observation = registry.execute(ToolCall(id="c1", name="echo", arguments={"wrong": "x"}))

    assert observation.ok is False
    assert observation.error.startswith("bad_arguments")


def test_path_guard_rejects_escape(tmp_path) -> None:
    registry = ToolRegistry(guard=ToolRegistry.path_guard(str(tmp_path)))
    registry.register(_spec("read"), lambda path: "content")

    inside = registry.execute(ToolCall(id="c1", name="read", arguments={"path": "notes.txt"}))
    outside = registry.execute(ToolCall(id="c2", name="read", arguments={"path": "../secret.txt"}))

    assert inside.ok is True
    assert outside.ok is False
    assert outside.error.startswith("guard_rejected")


def test_duplicate_registration_is_rejected() -> None:
    registry = ToolRegistry()
    registry.register(_spec(), lambda: "one")

    with pytest.raises(ValueError):
        registry.register(_spec(), lambda: "two")
