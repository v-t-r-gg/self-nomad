"""MCP middleware that enforces the recognized-tool envelope contract."""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp_types import CallToolResult, TextContent

from self_nomad.mcp_server.arguments import validate_tool_arguments
from self_nomad.mcp_server.tools import EXPECTED_TOOL_NAMES, fail_argument_errors

logger = logging.getLogger("self_nomad.mcp")


def _tool_call_parts(params: object) -> tuple[str | None, dict[str, Any] | None]:
    if params is None:
        return None, None
    if isinstance(params, dict):
        name = params.get("name")
        arguments = params.get("arguments")
    else:
        name = getattr(params, "name", None)
        arguments = getattr(params, "arguments", None)
    if name is not None and not isinstance(name, str):
        name = None
    if arguments is not None and not isinstance(arguments, dict):
        arguments = None
    return name, arguments


def _envelope_result(body: dict[str, Any]) -> CallToolResult:
    text = json.dumps(body, indent=2, sort_keys=False)
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structured_content=body,
        is_error=False,
    )


class EnvelopeBoundaryMiddleware:
    """Validate recognized-tool arguments and sanitize residual protocol errors.

    * Invalid arguments for tools in :data:`EXPECTED_TOOL_NAMES` return the
      self-nomad envelope (``ok: false``, ``MCP_INVALID_ARGUMENT``) instead of
      raw SDK / Pydantic text.
    * Residual ``is_error`` tool results for recognized tools are rewritten to
      a generic envelope so stack traces, paths, and input values never leave
      the server over the tool channel.
    * Unknown tool names are left to the MCP protocol layer.
    """

    async def __call__(
        self,
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
    ) -> HandlerResult:
        if ctx.method != "tools/call":
            return await call_next(ctx)

        tool_name, arguments = _tool_call_parts(ctx.params)
        if tool_name in EXPECTED_TOOL_NAMES:
            errors = validate_tool_arguments(tool_name, arguments)
            if errors:
                body = fail_argument_errors(tool_name, errors)
                return _envelope_result(body)

        result = await call_next(ctx)

        if (
            tool_name in EXPECTED_TOOL_NAMES
            and isinstance(result, CallToolResult)
            and result.is_error
        ):
            logger.error(
                "recognized tool %s returned protocol-level error; rewriting envelope",
                tool_name,
            )
            from self_nomad.mcp_server.models import ErrorItem

            body = fail_argument_errors(
                tool_name,
                [
                    ErrorItem(
                        code="MCP_INVALID_ARGUMENT",
                        message="invalid tool arguments",
                        path=None,
                    )
                ],
            )
            return _envelope_result(body)

        return result
