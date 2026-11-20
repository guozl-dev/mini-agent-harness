"""Interactive chat REPL over the harness.

Keeps multi-turn history, trims context, recalls memory each turn and records
episodes for later consolidation. No tools are registered here on purpose —
this is the "talk to it" entry point, not the task runner.

Usage:
    python scripts/chat.py                  # offline demo (scripted replies)
    python scripts/chat.py --provider env   # real model, needs LLM_* env vars

Commands:
    /exit       quit
    /clear      clear conversation history
    /memory X   show facts recalled for X
    /remember   consolidate this session's episodes into long-term facts
    /history    show how many turns are in context
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mini_harness.core.context import ContextManager  # noqa: E402
from mini_harness.core.memory import MemoryStore  # noqa: E402
from mini_harness.core.state import StateStore  # noqa: E402
from mini_harness.llm.provider import (  # noqa: E402
    FakeProvider,
    LLMProvider,
    OpenAICompatibleProvider,
    ProviderError,
)
from mini_harness.llm.types import Message  # noqa: E402

SYSTEM_PROMPT = (
    "你是运行在 mini-agent-harness 上的助手。回答简洁、先给结论；"
    "不确定时说明不确定，不要编造事实。"
)

FAKE_REPLIES = [
    "（离线演示模式）我在。这不是真实模型，只用来验证聊天链路是通的。",
    "（离线演示模式）配置 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 后，"
    "加 --provider env 就能接真实模型。",
    "（离线演示模式）我这个入口会保留多轮上下文，并把每轮对话记入情景记忆。",
]


def build_provider(kind: str) -> LLMProvider:
    if kind == "env":
        return OpenAICompatibleProvider.from_env()
    return FakeProvider(FAKE_REPLIES)


def extract_facts(provider: LLMProvider, transcript: str) -> str:
    """Ask the model to turn a transcript into fact JSON (used by /remember)."""
    return provider.complete(
        [
            Message(
                role="system",
                content=(
                    "从对话中提取稳定的用户事实，返回 JSON 数组："
                    '[{"text": "...", "key": "可选唯一键"}]，没有则返回 []。'
                ),
            ),
            Message(role="user", content=transcript),
        ]
    ).content


def main() -> int:
    parser = argparse.ArgumentParser(description="chat with the harness in a REPL")
    parser.add_argument("--provider", choices=["fake", "env"], default="fake")
    parser.add_argument("--session", default="default")
    args = parser.parse_args()

    try:
        provider = build_provider(args.provider)
    except ProviderError as exc:
        print(f"[config error] {exc}", file=sys.stderr)
        return 2

    memory = MemoryStore(ROOT / "agent_memory.sqlite")
    store = StateStore(ROOT / "agent_runs.sqlite")
    context = ContextManager(budget_tokens=3000, keep_recent=6)
    run_id = store.create_run(f"chat:{args.session}")
    history: list[Message] = []
    step = 0

    print("mini-agent-harness chat — 输入 /exit 退出，/remember 记住这次会话")
    print(f"provider={args.provider}  session={args.session}  run_id={run_id[:8]}\n")

    while True:
        try:
            user_input = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break
        if not user_input:
            continue
        if user_input in {"/exit", "/quit"}:
            print("再见。")
            break
        if user_input == "/clear":
            history.clear()
            print("（已清空本轮对话历史，长期记忆保留）")
            continue
        if user_input == "/history":
            print(f"（上下文中现有 {len(history)} 条消息）")
            continue
        if user_input.startswith("/memory"):
            query = user_input.removeprefix("/memory").strip() or "偏好"
            block = memory.context_block(query)
            print(block or "（没有相关记忆）")
            continue
        if user_input == "/remember":
            transcript = "\n".join(f"{m.role}: {m.content}" for m in history[-20:])
            written = memory.consolidate(
                args.session, lambda _text, _t=transcript: extract_facts(provider, _t)
            )
            print(f"（已巩固为长期事实：{written} 条）")
            continue

        block = memory.context_block(user_input)
        request = [Message(role="system", content=SYSTEM_PROMPT)]
        if block:
            request.append(Message(role="system", content=block))
        request.extend(history)
        request.append(Message(role="user", content=user_input))

        response = provider.complete(context.assemble(request))
        answer = response.content or "(空回复)"
        print(f"AI > {answer}\n")

        history.extend(
            [Message(role="user", content=user_input), Message(role="assistant", content=answer)]
        )
        memory.add_episode(args.session, f"用户: {user_input}\n助手: {answer}")
        step += 1
        snapshot = [m.model_dump(exclude_none=True) for m in history]
        store.save_step(run_id, step, "chat", snapshot)

    store.finish_run(run_id, "finished", f"{step} turns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
