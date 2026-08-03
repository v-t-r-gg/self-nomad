"""Focused tests for the authoritative MCP tool registrar."""

from __future__ import annotations

from typing import Any

import pytest

from self_nomad.mcp_server.errors import McpConfigurationError
from self_nomad.mcp_server.registry import ToolRegistrar
from self_nomad.mcp_server.tools import EXPECTED_TOOL_NAMES

pytest.importorskip("mcp")


def _annotations():  # type: ignore[no-untyped-def]
    from mcp_types import ToolAnnotations

    return ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )


def test_registrar_registers_seven_expected_tools() -> None:
    from mcp.server import MCPServer

    server = MCPServer(name="t", version="0")
    tools = ToolRegistrar(server)
    for name in EXPECTED_TOOL_NAMES:

        @tools.tool(name=name, description=name, annotations=_annotations())
        def _handler() -> dict[str, Any]:
            return {}

    tools.finalize()
    assert sorted(tools.registered) == sorted(EXPECTED_TOOL_NAMES)


def test_registrar_rejects_unknown_tool() -> None:
    from mcp.server import MCPServer

    server = MCPServer(name="t", version="0")
    tools = ToolRegistrar(server)
    with pytest.raises(McpConfigurationError, match="allow-list"):

        @tools.tool(
            name="self_nomad_approve",
            description="forbidden",
            annotations=_annotations(),
        )
        def _bad() -> dict[str, Any]:
            return {}


def test_registrar_rejects_duplicate() -> None:
    from mcp.server import MCPServer

    server = MCPServer(name="t", version="0")
    tools = ToolRegistrar(server)
    name = EXPECTED_TOOL_NAMES[0]

    @tools.tool(name=name, description=name, annotations=_annotations())
    def _first() -> dict[str, Any]:
        return {}

    with pytest.raises(McpConfigurationError, match="duplicate"):

        @tools.tool(name=name, description=name, annotations=_annotations())
        def _second() -> dict[str, Any]:
            return {}


def test_registrar_finalize_rejects_omission() -> None:
    from mcp.server import MCPServer

    server = MCPServer(name="t", version="0")
    tools = ToolRegistrar(server)
    # Register all but one.
    for name in EXPECTED_TOOL_NAMES[:-1]:

        @tools.tool(name=name, description=name, annotations=_annotations())
        def _handler() -> dict[str, Any]:
            return {}

    with pytest.raises(McpConfigurationError, match="allow-list"):
        tools.finalize()
