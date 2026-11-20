"""Phase 0 tests: provider behaviour and retry semantics (no network, no cost)."""

from __future__ import annotations

import pytest

from mini_harness.llm.provider import (
    FakeProvider,
    OpenAICompatibleProvider,
    ProviderError,
    with_retry,
)
from mini_harness.llm.types import ChatResponse, Message, ToolCall


def test_fake_provider_replays_script_in_order() -> None:
    provider = FakeProvider(["第一条", ChatResponse(content="第二条")])
    first = provider.complete([Message(role="user", content="hi")])
    second = provider.complete([Message(role="user", content="hi again")])
    assert first.content == "第一条"
    assert second.content == "第二条"
    assert len(provider.calls) == 2


def test_fake_provider_repeats_last_response() -> None:
    provider = FakeProvider(["唯一回复"])
    provider.complete([Message(role="user", content="1")])
    provider.complete([Message(role="user", content="2")])
    last = provider.complete([Message(role="user", content="3")])
    assert last.content == "唯一回复"


def test_chat_response_detects_tool_calls() -> None:
    response = ChatResponse(
        content="",
        tool_calls=[ToolCall(id="c1", name="run_tests", arguments={"path": "tests"})],
    )
    assert response.has_tool_calls is True
    assert ChatResponse(content="plain").has_tool_calls is False


def test_with_retry_succeeds_after_transient_failures() -> None:
    attempts = {"n": 0}
    sleeps: list[float] = []

    def flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise TimeoutError("temporary")
        return "ok"

    result = with_retry(flaky, max_retries=3, sleep=sleeps.append, jitter=lambda: 0.0)
    assert result == "ok"
    assert attempts["n"] == 3
    assert sleeps == [0.5, 1.0]  # 指数退避


def test_with_retry_raises_provider_error_after_exhausting() -> None:
    def always_fail() -> None:
        raise ConnectionError("down")

    with pytest.raises(ProviderError):
        with_retry(always_fail, max_retries=2, sleep=lambda _: None, jitter=lambda: 0.0)


def test_from_env_builds_provider(monkeypatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")

    provider = OpenAICompatibleProvider.from_env()

    assert provider.base_url == "https://api.deepseek.com/v1"
    assert provider.model == "deepseek-chat"


def test_from_env_reports_actionable_error(monkeypatch) -> None:
    for key in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ProviderError) as info:
        OpenAICompatibleProvider.from_env()

    assert "LLM_BASE_URL" in str(info.value)
    assert ".env.example" in str(info.value)
