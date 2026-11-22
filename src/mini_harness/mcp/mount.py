"""Start MCP servers and expose their tools through a ToolRegistry.

One ``MCPAdapt`` instance per server: failures stay isolated, and each server
keeps its own timeouts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mcpadapt.core import MCPAdapt

from ..core.tools import ToolRegistry
from .adapter import ToolRegistryAdapter
from .config import McpConfig, ServerConfig


@dataclass
class MountReport:
    mounted: dict[str, list[str]] = field(default_factory=dict)
    skipped: dict[str, list[str]] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)

    @property
    def tool_count(self) -> int:
        return sum(len(names) for names in self.mounted.values())


class MountedMcp:
    """Handle that owns the server processes for the duration of a run."""

    def __init__(self, handles: list[Any], report: MountReport) -> None:
        self._handles = handles
        self.report = report
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for handle in self._handles:
            try:
                handle.close()
            except Exception:  # noqa: BLE001 - shutdown must not raise
                pass
        self._handles.clear()

    def __enter__(self) -> MountedMcp:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def summary(self) -> str:
        parts = [f"{name}: {len(tools)} tools" for name, tools in self.report.mounted.items()]
        for name, reason in self.report.failed.items():
            parts.append(f"{name}: FAILED ({reason})")
        return "; ".join(parts) if parts else "no MCP servers"


def _mount_one(registry: ToolRegistry, server: ServerConfig) -> tuple[Any, ToolRegistryAdapter]:
    params = server.stdio_params()
    adapter = ToolRegistryAdapter(registry, server)
    handle = MCPAdapt(
        params,
        adapter,
        connect_timeout=int(server.connect_timeout_s),
        client_session_timeout_seconds=server.call_timeout_s,
    )
    handle.start()
    handle.tools()  # triggers adapter.adapt() for every announced tool
    return handle, adapter


def mount_mcp(registry: ToolRegistry, config: McpConfig) -> MountedMcp | None:
    """Start every enabled server; a broken server never blocks the others."""
    servers = config.enabled_servers()
    if not servers:
        return None

    handles: list[Any] = []
    report = MountReport()

    # The registry applies its own timeout around the callable; it must not be
    # shorter than the MCP round trip or healthy calls get killed.
    needed = config.max_call_timeout() + 5
    if registry.timeout_s < needed:
        registry.timeout_s = needed

    for server in servers:
        try:
            handle, adapter = _mount_one(registry, server)
        except Exception as exc:  # noqa: BLE001 - surfaced in the report
            report.failed[server.name] = f"{type(exc).__name__}: {exc}"
            continue
        handles.append(handle)
        report.mounted[server.name] = sorted(adapter.mounted)
        if adapter.skipped:
            report.skipped[server.name] = sorted(adapter.skipped)

    return MountedMcp(handles, report)
