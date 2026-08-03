"""Authoritative native MCP tool registration for the closed allow-list."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from mcp.server import MCPServer
from mcp_types import ToolAnnotations

from self_nomad.mcp_server.errors import McpConfigurationError
from self_nomad.mcp_server.tools import EXPECTED_TOOL_NAMES

logger = logging.getLogger("self_nomad.mcp")

_F = TypeVar("_F", bound=Callable[..., Any])


class ToolRegistrar:
    """Register native tools through one path that owns accounting.

    Every native tool must be registered via :meth:`tool`. Direct
    ``server.tool()`` calls outside this class are not part of the allow-list
    contract. Registration is recorded only after the SDK decorator succeeds.
    """

    def __init__(self, server: MCPServer) -> None:
        self._server = server
        self.registered: list[str] = []

    def tool(
        self,
        *,
        name: str,
        description: str,
        annotations: ToolAnnotations,
        structured_output: bool = True,
    ) -> Callable[[_F], _F]:
        if name not in EXPECTED_TOOL_NAMES:
            raise McpConfigurationError(
                "refusing to register tool outside the allow-list"
            )
        if name in self.registered:
            raise McpConfigurationError("duplicate tool registration")

        sdk_decorator = self._server.tool(
            name=name,
            description=description,
            annotations=annotations,
            structured_output=structured_output,
        )

        def decorator(fn: _F) -> _F:
            decorated: _F = sdk_decorator(fn)
            self.registered.append(name)
            return decorated

        return decorator

    def finalize(self) -> None:
        """Fail closed unless the recorded set matches the expected allow-list."""
        recorded = sorted(self.registered)
        expected = sorted(EXPECTED_TOOL_NAMES)
        if recorded != expected:
            logger.error("tool registry mismatch: %s != %s", recorded, expected)
            raise McpConfigurationError(
                "MCP tool registry does not match the expected allow-list"
            )
