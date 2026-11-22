"""Parse and validate MCP server definitions.

Only stdio transport is supported today: it is the one every MCP server ships
with, and it keeps the trust boundary simple (a local child process, not a
remote endpoint).
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp import StdioServerParameters

# Child processes must not inherit the whole environment: it would hand
# LLM_API_KEY (and every other secret) to a third-party server.
_ENV_WHITELIST = (
    "PATH",
    "PATHEXT",
    "SystemRoot",
    "SystemDrive",
    "COMSPEC",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "HOME",
    "LANG",
)


class McpConfigError(ValueError):
    """Invalid MCP configuration; message states what to fix."""


@dataclass(frozen=True)
class ServerConfig:
    name: str
    command: str
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None
    enabled: bool = True
    # Empty tuple = expose every tool the server announces.
    allowed_tools: tuple[str, ...] = ()
    # MCP servers legitimately touch paths outside the workspace.
    guard_exempt: bool = True
    connect_timeout_s: float = 30.0
    call_timeout_s: float = 60.0
    max_output_chars: int = 4000

    def stdio_params(self) -> StdioServerParameters:
        env = {key: os.environ[key] for key in _ENV_WHITELIST if key in os.environ}
        env.update(self.env)
        return StdioServerParameters(
            command=self.command,
            args=list(self.args),
            env=env,
            cwd=self.cwd,
        )


@dataclass(frozen=True)
class McpConfig:
    servers: tuple[ServerConfig, ...] = ()

    def enabled_servers(self) -> tuple[ServerConfig, ...]:
        return tuple(server for server in self.servers if server.enabled)

    def max_call_timeout(self) -> float:
        return max((server.call_timeout_s for server in self.enabled_servers()), default=0.0)


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list | tuple):
        return tuple(str(item) for item in value)
    raise McpConfigError(f"expected a string or list, got {type(value).__name__}")


def _server_from_dict(raw: dict[str, Any], index: int) -> ServerConfig:
    name = str(raw.get("name", "")).strip()
    if not name:
        raise McpConfigError(f"mcp.servers[{index}].name is required")

    command = str(raw.get("command", "")).strip()
    if not command:
        raise McpConfigError(f"server '{name}': command is required (e.g. 'npx.cmd')")
    if os.name == "nt" and command.lower() in {"npx", "uvx"}:
        raise McpConfigError(
            f"server '{name}': on Windows use '{command}.cmd'; a bare '{command}' "
            "is a shim that subprocess cannot execute directly"
        )

    connect_timeout = float(raw.get("connect_timeout_s", 30))
    call_timeout = float(raw.get("call_timeout_s", 60))
    if connect_timeout <= 0 or call_timeout <= 0:
        raise McpConfigError(f"server '{name}': timeouts must be > 0")

    output_chars = int(raw.get("max_output_chars", 4000))
    if output_chars < 200:
        raise McpConfigError(f"server '{name}': max_output_chars must be >= 200")

    env_raw = raw.get("env") or {}
    if not isinstance(env_raw, dict):
        raise McpConfigError(f"server '{name}': env must be a table")

    return ServerConfig(
        name=name,
        command=command,
        args=_as_tuple(raw.get("args")),
        env={str(k): str(v) for k, v in env_raw.items()},
        cwd=str(raw["cwd"]) if raw.get("cwd") else None,
        enabled=bool(raw.get("enabled", True)),
        allowed_tools=_as_tuple(raw.get("allowed_tools")),
        guard_exempt=bool(raw.get("guard_exempt", True)),
        connect_timeout_s=connect_timeout,
        call_timeout_s=call_timeout,
        max_output_chars=output_chars,
    )


def load_mcp_config(path: str | Path) -> McpConfig:
    config_path = Path(path).expanduser()
    if not config_path.is_file():
        raise McpConfigError(f"MCP config not found: {config_path}")

    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise McpConfigError(f"{config_path} is not valid TOML: {exc}") from exc

    raw_servers = (data.get("mcp") or {}).get("servers") or []
    if not isinstance(raw_servers, list):
        raise McpConfigError("mcp.servers must be an array of tables")

    servers = tuple(_server_from_dict(item, i) for i, item in enumerate(raw_servers))
    seen: set[str] = set()
    for server in servers:
        if server.name in seen:
            raise McpConfigError(f"duplicate server name: {server.name}")
        seen.add(server.name)
    return McpConfig(servers=servers)
