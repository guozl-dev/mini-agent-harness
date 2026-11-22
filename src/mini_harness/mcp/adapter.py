"""Adapt MCP tools into ``ToolRegistry`` entries.

One adapter instance serves one server: the MCP tool object carries no server
identity, so namespacing (``mcp__<server>__<tool>``) has to come from here.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from mcpadapt.core import ToolAdapter

from ..core.tools import ToolRegistry
from ..llm.types import ToolSpec
from .config import ServerConfig

_MAX_NAME = 64  # OpenAI-compatible function name limit
_SAFE = re.compile(r"[^A-Za-z0-9_-]")


def tool_name(server: str, tool: str) -> str:
    """``mcp__<server>__<tool>``, sanitized and length-capped with a hash suffix."""
    name = _SAFE.sub("_", f"mcp__{server}__{tool}")
    if len(name) <= _MAX_NAME:
        return name
    digest = hashlib.sha1(f"{server}:{tool}".encode()).hexdigest()[:6]
    return f"{name[: _MAX_NAME - 7]}_{digest}"


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = limit // 2
    tail = limit - head
    return f"{text[:head]}\n...({len(text) - limit} chars truncated)...\n{text[-tail:]}"


def flatten_content(content: Any, *, max_chars: int) -> str:
    """Collapse MCP content blocks into the plain text the harness stores."""
    parts: list[str] = []
    for block in content or []:
        kind = getattr(block, "type", None)
        if kind == "text":
            parts.append(str(getattr(block, "text", "")))
        elif kind == "image":
            mime = getattr(block, "mimeType", "image/*")
            data = getattr(block, "data", "") or ""
            parts.append(f"[image {mime}, ~{max(1, len(data) * 3 // 4)} bytes omitted]")
        elif kind == "resource":
            resource = getattr(block, "resource", None)
            uri = getattr(resource, "uri", "")
            text = getattr(resource, "text", None)
            parts.append(f"[resource {uri}]" + (f"\n{text}" if text else ""))
        else:
            parts.append(f"[{kind or 'unknown'} content omitted]")
    return _truncate("\n".join(part for part in parts if part).strip(), max_chars)


class ToolRegistryAdapter(ToolAdapter):
    """Register each announced MCP tool as a synchronous registry entry."""

    def __init__(self, registry: ToolRegistry, server: ServerConfig) -> None:
        self.registry = registry
        self.server = server
        self.mounted: set[str] = set()
        self.skipped: set[str] = set()

    def adapt(self, func, mcp_tool) -> ToolSpec | None:  # type: ignore[override]
        raw_name = str(getattr(mcp_tool, "name", "") or "")
        if not raw_name:
            return None
        if self.server.allowed_tools and raw_name not in self.server.allowed_tools:
            self.skipped.add(raw_name)
            return None

        name = tool_name(self.server.name, raw_name)
        if self.registry.has(name):  # MCPAdapt re-lists tools on every .tools() call
            return None

        schema = getattr(mcp_tool, "inputSchema", None) or {"type": "object", "properties": {}}
        description = (
            str(getattr(mcp_tool, "description", "") or "").strip()
            or f"[MCP:{self.server.name}] {raw_name}"
        )
        spec = ToolSpec(name=name, description=description, parameters=schema)

        def _call(**kwargs: Any) -> str:
            # MCPAdapt hands us ``func(arguments: dict | None)``, not **kwargs.
            result = func(kwargs or {})
            text = flatten_content(
                getattr(result, "content", None), max_chars=self.server.max_output_chars
            )
            if getattr(result, "isError", False):
                raise RuntimeError(text or "MCP tool reported an error")
            return text or "(empty result)"

        self.registry.register(
            spec,
            _call,
            guard_exempt=self.server.guard_exempt,
        )
        self.mounted.add(name)
        return spec
