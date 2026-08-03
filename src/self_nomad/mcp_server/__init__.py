"""Bounded local MCP surface for repository inspection and proposal intake.

Building or running the server requires the optional ``mcp`` extra::

    pip install 'self-nomad[mcp]'

Importing this package alone does not load the MCP SDK; ``build_server`` and
``main`` import it lazily/at call time for the server path.
"""

from __future__ import annotations

__all__ = ["EXPECTED_TOOL_NAMES", "build_server"]


def __getattr__(name: str) -> object:
    if name == "build_server":
        from self_nomad.mcp_server.server import build_server

        return build_server
    if name == "EXPECTED_TOOL_NAMES":
        from self_nomad.mcp_server.tools import EXPECTED_TOOL_NAMES

        return EXPECTED_TOOL_NAMES
    raise AttributeError(name)
