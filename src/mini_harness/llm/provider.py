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
import os
import random
import time
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

from .types import ChatResponse, Message, ToolCall, ToolSpec

T = TypeVar("T")


class ProviderError(RuntimeError):
    """Raised when the provider cannot produce a response after retries."""


def serialize_messages(messages: Sequence[Message]) -> list[dict[str, Any]]:
    """Convert internal messages to the OpenAI wire format.

    An assistant turn that requested tools must echo those ``tool_calls`` back;
    otherwise the provider rejects the following ``role="tool"`` message as
    orphaned (DeepSeek/OpenAI both enforce this).
    """
    wire: list[dict[str, Any]] = []
    for message in messages:
        item = message.model_dump(exclude_none=True)
        if message.role == "assistant" and message.tool_calls:
            item["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                }
                for call in message.tool_calls
            ]
        wire.append(item)
    return wire


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

        self.base_url = base_url.rstrip("/")
        self._model = model
        self._max_retries = max_retries
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    @property
    def model(self) -> str:
        return self._model

    @classmethod
    def from_env(cls, *, prefix: str = "LLM_") -> OpenAICompatibleProvider:
        """Build a provider from ``LLM_BASE_URL`` / ``LLM_API_KEY`` / ``LLM_MODEL``.

        See ``.env.example`` for the expected shape. Raises ``ProviderError`` with
        an actionable message when a variable is missing, so onboarding failures
        are self-explaining instead of a 401 three layers deep.
        """
        keys = ("BASE_URL", "API_KEY", "MODEL")
        values = {key: os.environ.get(f"{prefix}{key}") for key in keys}
        missing = [f"{prefix}{key}" for key, value in values.items() if not value]
        if missing:
            raise ProviderError(
                "missing environment variables: "
                + ", ".join(missing)
                + "; copy .env.example and export them first"
            )
        return cls(
            base_url=str(values["BASE_URL"]),
            api_key=str(values["API_KEY"]),
            model=str(values["MODEL"]),
            timeout=float(os.environ.get(f"{prefix}TIMEOUT", "60")),
            max_retries=int(os.environ.get(f"{prefix}MAX_RETRIES", "3")),
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
            "messages": serialize_messages(messages),
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
        raw_content = choice.get("content")
        if isinstance(raw_content, list):
            # Some gateways return content parts: [{"type": "text", "text": "..."}]
            content = "".join(
                part.get("text", "") for part in raw_content if isinstance(part, dict)
            )
        else:
            content = raw_content or ""
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
            content=content,
            tool_calls=tool_calls,
            model=data.get("model"),
            usage=data.get("usage") or {},
        )
