"""MCP (Model Context Protocol) integration for the harness.

Design: MCP tools are adapted into ordinary ``ToolRegistry`` entries, so the
agent loop and the tool registry need no MCP-specific logic.

Modules:
- ``config``  : parse TOML server definitions into validated settings
- ``adapter`` : convert one MCP tool into a (ToolSpec, callable) pair
- ``mount``   : start servers, register their tools, own the lifecycle
"""

from .config import McpConfig, McpConfigError, ServerConfig, load_mcp_config
from .mount import MountedMcp, mount_mcp

__all__ = [
    "McpConfig",
    "McpConfigError",
    "ServerConfig",
    "load_mcp_config",
    "MountedMcp",
    "mount_mcp",
]
