"""Run one agent task from the command line.

Default uses a scripted FakeProvider (zero cost, no API key). Pass
``--provider env`` after exporting LLM_BASE_URL / LLM_API_KEY / LLM_MODEL to
talk to a real model.

Usage:
    python scripts/run_agent.py --task "报一下现在几点"
    python scripts/run_agent.py --provider env --task "用一句话介绍你自己"
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mini_harness.core.loop import AgentLoop  # noqa: E402
from mini_harness.core.memory import MemoryStore  # noqa: E402
from mini_harness.core.state import StateStore  # noqa: E402
from mini_harness.core.tools import ToolRegistry  # noqa: E402
from mini_harness.llm.provider import (  # noqa: E402
    FakeProvider,
    OpenAICompatibleProvider,
    ProviderError,
)
from mini_harness.llm.types import ChatResponse, ToolCall, ToolSpec  # noqa: E402

DEFAULT_TASK = "用一句话说明你能做什么，并调用 now 工具报出当前时间"


def build_registry() -> ToolRegistry:
    registry = ToolRegistry(timeout_s=3)
    registry.register(
        ToolSpec(
            name="now",
            description="return current local time in ISO format",
            parameters={"type": "object", "properties": {}},
        ),
        lambda: datetime.now().isoformat(timespec="seconds"),
    )
    return registry


def build_provider(kind: str):
    if kind == "env":
        return OpenAICompatibleProvider.from_env()
    return FakeProvider(
        [
            ChatResponse(
                content="我先看一下时间。",
                tool_calls=[ToolCall(id="c1", name="now", arguments={})],
            ),
            ChatResponse(
                content="我是 mini-agent-harness：一个可审计、可恢复的轻量 Agent 运行时。"
            ),
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="run one agent task")
    parser.add_argument("--task", default=DEFAULT_TASK)
    parser.add_argument("--provider", choices=["fake", "env"], default="fake")
    parser.add_argument("--max-steps", type=int, default=6)
    args = parser.parse_args()

    try:
        provider = build_provider(args.provider)
    except ProviderError as exc:
        print(f"[config error] {exc}", file=sys.stderr)
        return 2

    loop = AgentLoop(
        provider,
        tools=build_registry(),
        store=StateStore(ROOT / "agent_runs.sqlite"),
        memory=MemoryStore(ROOT / "agent_memory.sqlite"),
        max_steps=args.max_steps,
    )
    result = loop.run(args.task)

    print(f"status : {result.status}")
    print(f"steps  : {result.steps}")
    print(f"answer : {result.content}")
    record = loop.history(result.run_id)
    for call in record.tool_calls:
        print(f"tool   : {call.name} ok={call.ok} output={call.output or call.error}")
    print(f"run_id : {result.run_id}")
    return 0 if result.status == "finished" else 1


if __name__ == "__main__":
    raise SystemExit(main())
