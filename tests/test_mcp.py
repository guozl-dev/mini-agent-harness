"""Integration tests for the MCP bridge.

Each test spawns the echo fixture as a real stdio MCP server, so these cover
the handshake, tool discovery, dispatch and error paths end to end.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from mini_harness.core.tools import ToolRegistry
from mini_harness.llm.types import ToolCall
from mini_harness.mcp import McpConfig, McpConfigError, ServerConfig, load_mcp_config, mount_mcp
from mini_harness.mcp.adapter import flatten_content, tool_name

FIXTURE = Path(__file__).parent / "fixtures" / "echo_server.py"


def make_server(**overrides) -> ServerConfig:
    base = {
        "name": "echo",
        "command": sys.executable,
        "args": (str(FIXTURE),),
        "connect_timeout_s": 60.0,
        "call_timeout_s": 60.0,
    }
    base.update(overrides)
    return ServerConfig(**base)


@pytest.fixture
def mounted():
    registry = ToolRegistry(timeout_s=30)
    handle = mount_mcp(registry, McpConfig(servers=(make_server(),)))
    assert handle is not None
    yield registry, handle
    handle.close()


def test_tools_are_registered_with_namespace(mounted):
    registry, handle = mounted
    names = set(registry.names())
    assert {"mcp__echo__echo", "mcp__echo__add", "mcp__echo__boom"} <= names
    assert handle.report.failed == {}
    assert handle.report.tool_count == len(handle.report.mounted["echo"])


def test_call_returns_text(mounted):
    registry, _ = mounted
    result = registry.execute(
        ToolCall(id="c1", name="mcp__echo__echo", arguments={"text": "hello-mcp"})
    )
    assert result.ok is True, result.error
    assert result.output == "hello-mcp"
    assert result.duration_ms >= 0


def test_tool_error_becomes_observation(mounted):
    registry, _ = mounted
    result = registry.execute(ToolCall(id="c2", name="mcp__echo__boom", arguments={}))
    assert result.ok is False
    assert "boom" in result.error.lower()


def test_unknown_tool_is_reported(mounted):
    registry, _ = mounted
    result = registry.execute(ToolCall(id="c3", name="mcp__echo__nope", arguments={}))
    assert result.ok is False
    assert "tool_not_found" in result.error


def test_allowlist_hides_other_tools():
    registry = ToolRegistry(timeout_s=30)
    handle = mount_mcp(
        registry,
        McpConfig(servers=(make_server(allowed_tools=("echo",)),)),
    )
    try:
        assert "mcp__echo__echo" in registry.names()
        assert "mcp__echo__add" not in registry.names()
        assert handle.report.skipped["echo"] == ["add", "boom", "slow"]
    finally:
        handle.close()


def test_mounting_twice_does_not_duplicate_tools():
    registry = ToolRegistry(timeout_s=30)
    config = McpConfig(servers=(make_server(),))
    first = mount_mcp(registry, config)
    count = len(registry.names())
    second = mount_mcp(registry, config)
    try:
        assert len(registry.names()) == count
        assert second.report.tool_count == 0
    finally:
        first.close()
        second.close()


def test_loop_invokes_mcp_tool(mounted, tmp_path):
    """The agent loop needs no MCP awareness: it just calls a registry entry."""
    from mini_harness.core.loop import AgentLoop
    from mini_harness.core.state import StateStore
    from mini_harness.llm.provider import FakeProvider
    from mini_harness.llm.types import ChatResponse

    registry, _ = mounted
    provider = FakeProvider(
        [
            ChatResponse(
                content="先调用 echo",
                tool_calls=[
                    ToolCall(id="c1", name="mcp__echo__echo", arguments={"text": "via-loop"})
                ],
            ),
            ChatResponse(content="完成"),
        ]
    )
    loop = AgentLoop(
        provider,
        tools=registry,
        store=StateStore(tmp_path / "runs.sqlite"),
        max_steps=3,
    )

    result = loop.run("echo via-loop")

    assert result.status == "finished"
    calls = loop.history(result.run_id).tool_calls
    assert calls[0].name == "mcp__echo__echo"
    assert calls[0].output == "via-loop"


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_broken_server_is_isolated_and_reported():
    registry = ToolRegistry(timeout_s=30)
    bad = make_server(
        name="broken",
        command=sys.executable,
        args=("-c", "raise SystemExit(3)"),
        connect_timeout_s=5.0,
    )
    handle = mount_mcp(registry, McpConfig(servers=(bad, make_server())))
    try:
        assert "broken" in handle.report.failed
        assert "mcp__echo__echo" in registry.names()
    finally:
        handle.close()


def test_registry_timeout_is_raised_for_mcp():
    registry = ToolRegistry(timeout_s=3)
    handle = mount_mcp(registry, McpConfig(servers=(make_server(call_timeout_s=45),)))
    try:
        assert registry.timeout_s >= 50
    finally:
        handle.close()


def test_tool_name_is_sanitized_and_capped():
    assert tool_name("fs", "read.file") == "mcp__fs__read_file"
    long_name = tool_name("server-" + "x" * 40, "t" * 40)
    assert len(long_name) <= 64
    assert long_name.startswith("mcp__")


def test_flatten_handles_image_and_resource():
    class Block:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    content = [
        Block(type="text", text="hi"),
        Block(type="image", mimeType="image/png", data="A" * 400),
        Block(type="resource", resource=Block(uri="file:///a.txt", text="body")),
    ]
    text = flatten_content(content, max_chars=4000)
    assert "hi" in text
    assert "[image image/png" in text
    assert "file:///a.txt" in text and "body" in text


def test_config_rejects_bare_npx_on_windows(tmp_path):
    cfg = tmp_path / "mcp.toml"
    cfg.write_text(
        '[[mcp.servers]]\nname = "fs"\ncommand = "npx"\nargs = ["-y", "server"]\n',
        encoding="utf-8",
    )
    if sys.platform != "win32":
        pytest.skip("Windows-specific validation")
    with pytest.raises(McpConfigError, match=r"npx\.cmd"):
        load_mcp_config(cfg)


def test_config_rejects_duplicate_names(tmp_path):
    cfg = tmp_path / "mcp.toml"
    cfg.write_text(
        '[[mcp.servers]]\nname = "a"\ncommand = "python"\n'
        '[[mcp.servers]]\nname = "a"\ncommand = "python"\n',
        encoding="utf-8",
    )
    with pytest.raises(McpConfigError, match="duplicate"):
        load_mcp_config(cfg)


def test_config_rejects_missing_command(tmp_path):
    cfg = tmp_path / "mcp.toml"
    cfg.write_text('[[mcp.servers]]\nname = "a"\n', encoding="utf-8")
    with pytest.raises(McpConfigError, match="command is required"):
        load_mcp_config(cfg)
