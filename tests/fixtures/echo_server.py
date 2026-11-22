"""Minimal MCP server used by the integration tests.

Run directly to speak stdio:  python tests/fixtures/echo_server.py
"""

from __future__ import annotations

import time

from mcp.server.fastmcp import FastMCP

server = FastMCP("echo-fixture")


@server.tool()
def echo(text: str) -> str:
    """Return the input text unchanged."""
    return text


@server.tool()
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@server.tool()
def boom() -> str:
    """Always raises, to exercise the isError path."""
    raise RuntimeError("boom from fixture")


@server.tool()
def slow(seconds: float = 5.0) -> str:
    """Sleep, then return 'done'. Used for timeout tests."""
    time.sleep(seconds)
    return "done"


if __name__ == "__main__":
    server.run()
