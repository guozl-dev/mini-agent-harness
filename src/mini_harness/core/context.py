"""Context budget management: externalize, summarize, hard-trim.

Strategy ladder (applied in order until the budget fits):
1. externalize  — oversized tool results move out of context, leaving a handle;
2. summarize    — older turns collapse into one rolling summary message;
3. hard trim    — drop the oldest non-system messages as a last resort.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from ..llm.types import Message


def estimate_tokens(text: str) -> int:
    """Rough token estimate (CJK-heavy text ≈ 1 token per 2-3 chars).

    Deliberately dependency-free and deterministic; swap for tiktoken later
    without changing the call sites.
    """
    if not text:
        return 0
    return len(text) // 3 + 1


def _message_tokens(message: Message) -> int:
    return estimate_tokens(message.content) + 4  # role/format overhead


class ContextManager:
    def __init__(
        self,
        *,
        budget_tokens: int = 3000,
        keep_recent: int = 4,
        externalize_over_chars: int = 600,
        summarizer: Callable[[str], str] | None = None,
    ) -> None:
        if keep_recent < 1:
            raise ValueError("keep_recent must be >= 1")
        self.budget_tokens = budget_tokens
        self.keep_recent = keep_recent
        self.externalize_over_chars = externalize_over_chars
        self.summarizer = summarizer
        # Observability for tests and demos
        self.externalized: dict[int, str] = {}
        self.last_summary: str | None = None
        self.trim_events: list[str] = []

    # -- public ---------------------------------------------------------
    def estimate(self, messages: Sequence[Message]) -> int:
        return sum(_message_tokens(m) for m in messages)

    def assemble(self, messages: Sequence[Message]) -> list[Message]:
        working = self._externalize(list(messages))
        if self.estimate(working) <= self.budget_tokens:
            return working
        working = self._summarize(working)
        if self.estimate(working) <= self.budget_tokens:
            return working
        return self._hard_trim(working)

    # -- steps ----------------------------------------------------------
    def _externalize(self, messages: list[Message]) -> list[Message]:
        for idx, message in enumerate(messages):
            if message.role == "tool" and len(message.content) > self.externalize_over_chars:
                digest = message.content[:80].replace("\n", " ")
                self.externalized[idx] = message.content
                messages[idx] = message.model_copy(
                    update={"content": f"[tool result externalized: {len(message.content)} chars] "
                                       f"head={digest}..."}
                )
                self.trim_events.append(f"externalized step {idx}")
        return messages

    def _summarize(self, messages: list[Message]) -> list[Message]:
        system = [m for m in messages if m.role == "system"]
        rest = [m for m in messages if m.role != "system"]
        if len(rest) <= self.keep_recent:
            return messages
        head, tail = rest[: -self.keep_recent], rest[-self.keep_recent :]
        joined = "\n".join(f"{m.role}: {m.content}" for m in head if m.content)
        if self.summarizer is not None:
            summary = self.summarizer(joined)
        else:
            summary = joined[:200] + "..." if len(joined) > 200 else joined
        self.last_summary = summary
        self.trim_events.append(f"summarized {len(head)} messages")
        return [*system, Message(role="system", content=f"[历史摘要] {summary}"), *tail]

    def _hard_trim(self, messages: list[Message]) -> list[Message]:
        system = [m for m in messages if m.role == "system"]
        rest = [m for m in messages if m.role != "system"]
        while rest and self.estimate(system + rest) > self.budget_tokens:
            rest.pop(0)
            self.trim_events.append("hard-trimmed one message")
        return system + rest
