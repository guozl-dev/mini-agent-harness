"""Phase 4 e2e test: loop + tool + sandbox + memory in one chain."""

from __future__ import annotations

from mini_harness.core.loop import AgentLoop
from mini_harness.core.memory import MemoryStore
from mini_harness.core.sandbox import SandboxRunner
from mini_harness.core.state import StateStore
from mini_harness.core.tools import ToolRegistry
from mini_harness.llm.provider import FakeProvider
from mini_harness.llm.types import ChatResponse, ToolCall, ToolSpec

BUGGY = "def add(a, b):\n    return a - b\n"
TEST = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"


def _project(tmp_path):
    (tmp_path / "calc.py").write_text(BUGGY, encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_calc.py").write_text(TEST, encoding="utf-8")
    return tmp_path


def test_agent_runs_tests_as_a_tool_and_records_memory(tmp_path) -> None:
    project = _project(tmp_path)
    runner = SandboxRunner(project)

    def run_tests() -> str:
        result = runner.run()
        return f"passed={result.passed} failed={result.failed}"

    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="run_tests", description="run pytest", parameters={"type": "object"}),
        run_tests,
    )
    provider = FakeProvider(
        [
            ChatResponse(
                content="先跑测试看看",
                tool_calls=[ToolCall(id="c1", name="run_tests", arguments={})],
            ),
            ChatResponse(content="看到 1 个失败用例，需要修 add 的实现"),
        ]
    )
    memory = MemoryStore()
    memory.add_fact("用户偏好中文回答")
    loop = AgentLoop(provider, tools=registry, store=StateStore(), memory=memory)

    result = loop.run("用中文回答：帮我检查这个项目为什么测试失败")

    assert result.status == "finished"
    assert result.steps == 2
    assert "1 个失败" in result.content

    record = loop.history(result.run_id)
    assert record.tool_calls[0].ok is True
    assert "failed=1" in (record.tool_calls[0].output or "")
    assert len(memory.episodes(result.run_id)) == 1
    assert any("记忆" in message.content for message in provider.calls[0])
