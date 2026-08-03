"""Unit tests for envelope boundary middleware."""

from __future__ import annotations

import json
from typing import Any

import pytest

from self_nomad.mcp_server.middleware import EnvelopeBoundaryMiddleware
from self_nomad.mcp_server.tools import EXPECTED_TOOL_NAMES

pytest.importorskip("mcp")


class _Ctx:
    def __init__(self, method: str, params: dict[str, Any] | None) -> None:
        self.method = method
        self.params = params
        self.request_id = 1


@pytest.mark.asyncio
async def test_residual_is_error_becomes_internal_envelope() -> None:
    from mcp_types import CallToolResult, TextContent

    mw = EnvelopeBoundaryMiddleware()
    leak = (
        "Traceback (most recent call last):\n"
        '  File "/tmp/staging/worktree/handler.py", line 1\n'
        "Authorization: Bearer sk-live-SHOULD-NOT-LEAK\n"
    )
    tool = EXPECTED_TOOL_NAMES[0]

    async def call_next(_ctx: object) -> CallToolResult:
        return CallToolResult(
            content=[TextContent(type="text", text=leak)],
            is_error=True,
        )

    result = await mw(
        _Ctx("tools/call", {"name": tool, "arguments": {}}),  # type: ignore[arg-type]
        call_next,
    )
    assert isinstance(result, CallToolResult)
    assert result.is_error is False
    body = result.structured_content
    assert body is not None
    assert body["ok"] is False
    assert body["errors"][0]["code"] == "MCP_INTERNAL_ERROR"
    assert body["errors"][0]["message"] == "an internal error occurred"
    serialized = json.dumps(body) + "".join(
        getattr(block, "text", "") or "" for block in result.content
    )
    assert "sk-live" not in serialized
    assert "/tmp/staging" not in serialized
    assert "Traceback" not in serialized
    assert "Bearer" not in serialized


@pytest.mark.asyncio
async def test_invalid_arguments_remain_invalid_argument_code() -> None:
    from mcp_types import CallToolResult

    mw = EnvelopeBoundaryMiddleware()
    called = False

    async def call_next(_ctx: object) -> CallToolResult:
        nonlocal called
        called = True
        raise AssertionError("handler must not run for invalid args")

    result = await mw(
        _Ctx(  # type: ignore[arg-type]
            "tools/call",
            {
                "name": "self_nomad_proposal_get",
                "arguments": {"proposal_id": "not-a-uuid"},
            },
        ),
        call_next,
    )
    assert called is False
    assert isinstance(result, CallToolResult)
    body = result.structured_content
    assert body is not None
    assert body["ok"] is False
    assert body["errors"][0]["code"] == "MCP_INVALID_ARGUMENT"
