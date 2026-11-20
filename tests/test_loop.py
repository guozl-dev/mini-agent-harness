"""Phase 1 tests: loop state machine, persistence and resume."""

from __future__ import annotations

from mini_harness.core.loop import AgentLoop, LoopState
from mini_harness.core.state import StateStore
from mini_harness.core.tools import ToolRegistry
from mini_harness.llm.provider import FakeProvider
from mini_harness.llm.types import ChatResponse, Message, ToolCall, ToolSpec


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="echo", description="echo", parameters={"type": "object"}),
        lambda text: f"echo:{text}",
    )
    return registry


def test_direct_answer_finishes_in_one_step() -> None:
    loop = AgentLoop(FakeProvider(["done"]), store=StateStore())

    result = loop.run("say done")

    assert result.status == "finished"
    assert result.steps == 1
    assert result.content == "done"
    assert loop.state is LoopState.FINISHED
    assert loop.history(result.run_id).status == "finished"


def test_tool_call_then_answer_takes_two_steps() -> None:
    provider = FakeProvider(
        [
            ChatResponse(
                content="",
                tool_calls=[ToolCall(id="c1", name="echo", arguments={"text": "hi"})],
            ),
            ChatResponse(content="final"),
        ]
    )
    loop = AgentLoop(provider, tools=_registry(), store=StateStore())

    result = loop.run("echo hi then answer")

    assert result.status == "finished"
    assert result.steps == 2
    record = loop.history(result.run_id)
    assert [step.step_no for step in record.steps] == [1, 2]
    assert record.tool_calls[0].name == "echo"
    assert record.tool_calls[0].ok is True
    assert record.tool_calls[0].output == "echo:hi"


def test_failed_tool_becomes_observation_not_crash() -> None:
    provider = FakeProvider(
        [
            ChatResponse(
                content="",
                tool_calls=[ToolCall(id="c1", name="missing_tool", arguments={})],
            ),
            ChatResponse(content="recovered"),
        ]
    )
    loop = AgentLoop(provider, tools=_registry(), store=StateStore())

    result = loop.run("call a ghost tool")

    assert result.status == "finished"
    assert result.content == "recovered"
    assert loop.history(result.run_id).tool_calls[0].ok is False


def test_step_budget_exhaustion_fails_the_run() -> None:
    always_tool = ChatResponse(
        content="", tool_calls=[ToolCall(id="c1", name="echo", arguments={"text": "loop"})]
    )
    loop = AgentLoop(
        FakeProvider([always_tool]), tools=_registry(), store=StateStore(), max_steps=2
    )

    result = loop.run("never finish")

    assert result.status == "failed"
    assert result.steps == 2
    assert result.content == "max_steps_exceeded"
    assert loop.history(result.run_id).status == "failed"


def test_resume_continues_from_last_snapshot() -> None:
    store = StateStore()
    run_id = store.create_run("resume me")
    store.save_step(
        run_id,
        1,
        "planning",
        [
            Message(role="system", content="sys").model_dump(),
            Message(role="user", content="resume me").model_dump(),
        ],
    )
    loop = AgentLoop(FakeProvider(["picked up"]), store=store)

    result = loop.resume(run_id)

    assert result.status == "finished"
    assert result.steps == 2
    assert result.content == "picked up"


def test_resume_on_finished_run_returns_immediately() -> None:
    loop = AgentLoop(FakeProvider(["done"]), store=StateStore())
    finished = loop.run("task")

    again = loop.resume(finished.run_id)

    assert again.status == "finished"
    assert again.steps == 1
    assert again.content == "done"
