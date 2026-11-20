"""LLM provider abstraction with retry, timeout and a deterministic fake.

Design notes:
- Every network failure is bounded by (timeout, max_retries) and surfaces as
  ``ProviderError`` so the agent loop can turn it into an observation instead of
  crashing the run.
- ``FakeProvider`` keeps tests deterministic and free: the CI pipeline never
  calls a real model.
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

from .types import ChatResponse, Message, ToolCall, ToolSpec

T = TypeVar("T")


class ProviderError(RuntimeError):
    """Raised when the provider cannot produce a response after retries."""


def with_retry(
    fn: Callable[[], T],
    *,
    max_retries: int = 3,
    base_delay: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = random.random,
) -> T:
    """Retry ``fn`` with exponential backoff; raises ``ProviderError`` at the end."""
    last: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - retried below
            last = exc
            if attempt == max_retries:
                break
            delay = base_delay * (2**attempt) * (1 + jitter() * 0.1)
            sleep(delay)
    raise ProviderError(f"provider failed after {max_retries} retries: {last}") from last


class LLMProvider:
    """Minimal interface every provider implements."""

    def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] | None = None,
        *,
        temperature: float = 0.2,
    ) -> ChatResponse:  # pragma: no cover - interface
        raise NotImplementedError


class FakeProvider(LLMProvider):
    """Scripted provider used by tests and demos.

    Responses are popped in order; when exhausted, the last one repeats so a
    demo can run without stopping.
    """

    def __init__(self, script: Sequence[ChatResponse | str]) -> None:
        if not script:
            raise ValueError("script must contain at least one response")
        self._script: list[ChatResponse] = [
            item if isinstance(item, ChatResponse) else ChatResponse(content=item)
            for item in script
        ]
        self.calls: list[list[Message]] = []

    def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] | None = None,
        *,
        temperature: float = 0.2,
    ) -> ChatResponse:
        self.calls.append(list(messages))
        index = min(len(self.calls) - 1, len(self._script) - 1)
        return self._script[index]


class OpenAICompatibleProvider(LLMProvider):
    """Provider for any OpenAI-compatible endpoint (DeepSeek, Qwen, Ollama...)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        timeout: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        import httpx  # local import keeps the package importable without httpx

        self._model = model
        self._max_retries = max_retries
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] | None = None,
        *,
        temperature: float = 0.2,
    ) -> ChatResponse:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [m.model_dump(exclude_none=True) for m in messages],
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]

        def _call() -> ChatResponse:
            resp = self._client.post("/chat/completions", json=payload)
            resp.raise_for_status()
            return self._parse(resp.json())

        return with_retry(_call, max_retries=self._max_retries)

    def _parse(self, data: dict[str, Any]) -> ChatResponse:
        choice = data["choices"][0]["message"]
        tool_calls: list[ToolCall] = []
        for idx, call in enumerate(choice.get("tool_calls") or []):
            raw_args = call.get("function", {}).get("arguments") or "{}"
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                args = {"_raw": raw_args}
            tool_calls.append(
                ToolCall(
                    id=call.get("id") or f"call_{idx}",
                    name=call["function"]["name"],
                    arguments=args,
                )
            )
        return ChatResponse(
            content=choice.get("content") or "",
            tool_calls=tool_calls,
            model=data.get("model"),
            usage=data.get("usage") or {},
        )
