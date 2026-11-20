"""Data models shared by all providers and the agent loop."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant", "tool"]


class Message(BaseModel):
    """A single chat message."""

    role: Role
    content: str = ""
    name: str | None = None
    tool_call_id: str | None = None


class ToolSpec(BaseModel):
    """Tool declaration exposed to the model."""

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    """A tool invocation requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """Normalized model response."""

    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    model: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)
