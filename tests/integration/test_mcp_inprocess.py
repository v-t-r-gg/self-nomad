"""In-process MCP client tests against the bounded server."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from self_nomad.application import SelfNomad
from self_nomad.mcp_server.server import build_server
from self_nomad.mcp_server.tools import EXPECTED_TOOL_NAMES
from tests.helpers import configure_git_identity, run_git

pytest.importorskip("mcp")

pytestmark = pytest.mark.asyncio


def _repo(tmp_path: Path) -> Path:
    app = SelfNomad.initialize(tmp_path / "agent", name="mcp-inproc")
    configure_git_identity(app.repository.root)
    run_git(app.repository.root, "add", ".")
    run_git(app.repository.root, "commit", "-m", "initial")
    return app.repository.root


def _request(request_id: str = "mcp:memory:1", content: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "request_id": request_id,
        "reason": "Record a preference via MCP.",
        "source": {"runtime": "openclaw", "agent_identifier": "primary"},
        "operations": [
            {
                "kind": "replace",
                "path": "memory/MEMORY.md",
                "content": content
                if content is not None
                else "# Memory\n\n- Prefers MCP intake.\n",
            }
        ],
    }


@asynccontextmanager
async def _session(root: Path) -> AsyncIterator[tuple[Any, Any]]:
    from mcp import ClientSession
    from mcp.client._memory import InMemoryTransport

    server = build_server(root)
    async with (
        InMemoryTransport(server, raise_exceptions=True) as (read, write),
        ClientSession(read, write) as client,
    ):
        initialized = await client.initialize()
        yield client, initialized


def _body(result: Any) -> dict[str, Any]:
    assert result.is_error is False, getattr(result, "content", None)
    assert result.structured_content is not None
    return result.structured_content


def _assert_structured_actions(steps: list[Any]) -> None:
    bare = {"submit", "validate", "approve", "apply"}
    for step in steps:
        assert isinstance(step, dict)
        assert step.get("channel") in {"mcp", "cli", "cli_operator"}
        if step.get("channel") == "mcp":
            assert str(step.get("tool", "")).startswith("self_nomad_")
        assert step.get("tool") not in bare
        assert step.get("command") not in bare
        # Command may contain approve/apply as CLI verbs but not as bare strings only.
        if "command" in step:
            assert step["command"].startswith("self-nomad ")


async def test_server_identity_from_initialize(tmp_path: Path) -> None:
    from self_nomad import __version__

    async with _session(_repo(tmp_path)) as (client, initialized):
        assert initialized.server_info.name == "self-nomad"
        assert initialized.server_info.version == __version__
        tools = await client.list_tools()
        assert len(tools.tools) == 7


async def test_tool_discovery_exact_set(tmp_path: Path) -> None:
    async with _session(_repo(tmp_path)) as (client, _init):
        tools = await client.list_tools()
        names = sorted(tool.name for tool in tools.tools)
        assert names == sorted(EXPECTED_TOOL_NAMES)
        forbidden = (
            "approve",
            "apply",
            "reject",
            "restore",
            "import",
            "cleanup",
            "push",
            "execute",
        )
        for name in names:
            parts = set(name.split("_"))
            for word in forbidden:
                assert word not in parts, f"forbidden tool fragment {word!r} in {name}"
        by_name = {t.name: t for t in tools.tools}
        assert by_name["self_nomad_repository_status"].annotations.read_only_hint is True
        assert by_name["self_nomad_intake_submit"].annotations.read_only_hint is False
        assert by_name["self_nomad_intake_submit"].annotations.idempotent_hint is True
        for tool in tools.tools:
            assert tool.annotations is not None
            assert tool.annotations.open_world_hint is False
            assert tool.annotations.destructive_hint is False


async def test_repository_status_and_validate(tmp_path: Path) -> None:
    async with _session(_repo(tmp_path)) as (client, _init):
        status = await client.call_tool("self_nomad_repository_status", {})
        body = _body(status)
        assert body["ok"] is True
        assert body["schema_version"] == 1
        assert body["tool"] == "self_nomad_repository_status"
        assert body["result"]["repository"]["name"] == "mcp-inproc"
        assert body["result"]["proposals"]["total"] == 0

        validated = await client.call_tool(
            "self_nomad_repository_validate", {"strict": True}
        )
        body = _body(validated)
        assert body["ok"] is True
        assert body["result"]["valid"] is True


async def test_intake_preview_submit_list_get_validate(tmp_path: Path) -> None:
    async with _session(_repo(tmp_path)) as (client, _init):
        request = _request()

        preview = await client.call_tool(
            "self_nomad_intake_preview", {"request": request}
        )
        body = _body(preview)
        assert body["ok"] is True
        assert body["result"]["eligible"] is True
        assert "Prefers MCP" not in json.dumps(body)
        _assert_structured_actions(body["result"]["suggested_next"])
        assert body["result"]["suggested_next"] == [
            {
                "channel": "mcp",
                "tool": "self_nomad_intake_submit",
                "description": "Submit this eligible request",
            }
        ]

        submitted = await client.call_tool(
            "self_nomad_intake_submit", {"request": request}
        )
        body = _body(submitted)
        assert body["ok"] is True
        proposal_id = body["result"]["proposal_id"]
        assert body["result"]["reused"] is False
        _assert_structured_actions(body["result"]["suggested_next"])
        assert any(
            s.get("tool") == "self_nomad_proposal_validate"
            for s in body["result"]["suggested_next"]
        )

        again = await client.call_tool(
            "self_nomad_intake_submit", {"request": request}
        )
        body = _body(again)
        assert body["result"]["reused"] is True
        assert body["result"]["proposal_id"] == proposal_id
        _assert_structured_actions(body["result"]["suggested_next"])

        listed = await client.call_tool(
            "self_nomad_proposal_list", {"limit": 10, "status": "materialized"}
        )
        body = _body(listed)
        assert body["ok"] is True
        assert body["result"]["count"] >= 1
        for item in body["result"]["items"]:
            _assert_structured_actions(item["suggested_next"])

        got = await client.call_tool(
            "self_nomad_proposal_get", {"proposal_id": proposal_id}
        )
        body = _body(got)
        assert body["ok"] is True
        assert body["result"]["proposal_id"] == proposal_id
        assert "content_source" not in json.dumps(body)
        assert body["result"]["status"] == "materialized"
        steps = body["result"]["suggested_next"]
        _assert_structured_actions(steps)
        assert any(s.get("tool") == "self_nomad_proposal_validate" for s in steps)
        assert any(s.get("channel") == "cli_operator" for s in steps)

        validated = await client.call_tool(
            "self_nomad_proposal_validate", {"proposal_id": proposal_id}
        )
        body = _body(validated)
        assert body["ok"] is True
        assert body["result"]["status"] == "validated"
        _assert_structured_actions(body["result"]["suggested_next"])
        assert all(s.get("channel") == "cli_operator" for s in body["result"]["suggested_next"])

        again_val = await client.call_tool(
            "self_nomad_proposal_validate", {"proposal_id": proposal_id}
        )
        assert _body(again_val)["result"]["status"] == "validated"


async def test_schema_resource(tmp_path: Path) -> None:
    async with _session(_repo(tmp_path)) as (client, _init):
        resources = await client.list_resources()
        uris = [str(r.uri) for r in resources.resources]
        assert "self-nomad://schemas/proposal-request/v1" in uris
        content = await client.read_resource("self-nomad://schemas/proposal-request/v1")
        text = "".join(
            block.text
            for block in content.contents
            if hasattr(block, "text") and block.text
        )
        assert "schema_version" in text


async def test_stable_errors_for_missing_proposal(tmp_path: Path) -> None:
    async with _session(_repo(tmp_path)) as (client, _init):
        missing = str(uuid4())
        got = await client.call_tool(
            "self_nomad_proposal_get", {"proposal_id": missing}
        )
        body = _body(got)
        assert body["ok"] is False
        assert body["errors"][0]["code"] == "PROPOSAL_NOT_FOUND"
        assert body["errors"][0]["message"] == "proposal not found"


async def test_concurrent_identical_submissions(tmp_path: Path) -> None:
    request = _request("mcp:concurrent:1")
    async with _session(_repo(tmp_path)) as (client, _init):
        results = await asyncio.gather(
            client.call_tool("self_nomad_intake_submit", {"request": request}),
            client.call_tool("self_nomad_intake_submit", {"request": request}),
        )
    bodies = [_body(r) for r in results]
    assert all(b["ok"] for b in bodies)
    ids = {b["result"]["proposal_id"] for b in bodies}
    assert len(ids) == 1


async def test_preview_does_not_create_proposals(tmp_path: Path) -> None:
    async with _session(_repo(tmp_path)) as (client, _init):
        request = _request("mcp:preview-only:1")
        preview = await client.call_tool(
            "self_nomad_intake_preview", {"request": request}
        )
        assert _body(preview)["ok"] is True
        listed = await client.call_tool("self_nomad_proposal_list", {"limit": 50})
        assert _body(listed)["result"]["count"] == 0


async def test_id_conflict_error(tmp_path: Path) -> None:
    async with _session(_repo(tmp_path)) as (client, _init):
        request = _request("mcp:conflict:1")
        first = await client.call_tool(
            "self_nomad_intake_submit", {"request": request}
        )
        assert _body(first)["ok"] is True
        conflicted = dict(request)
        conflicted["reason"] = "Different payload same request_id"
        second = await client.call_tool(
            "self_nomad_intake_submit", {"request": conflicted}
        )
        body = _body(second)
        assert body["ok"] is False
        assert body["errors"][0]["code"] == "INTAKE_ID_CONFLICT"
        assert "Different payload" not in json.dumps(body)


async def test_invalid_arguments_use_envelope(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    secret = "Bearer sk-live-SHOULD-NOT-LEAK"
    async with _session(root) as (client, _init):
        cases: list[tuple[str, dict[str, Any], str]] = [
            ("self_nomad_proposal_get", {"proposal_id": "not-a-uuid"}, "proposal_id"),
            ("self_nomad_proposal_list", {"status": "nope"}, "status"),
            ("self_nomad_proposal_list", {"limit": -1}, "limit"),
            ("self_nomad_proposal_list", {"limit": 9999}, "limit"),
            ("self_nomad_proposal_list", {"cursor": "%%%"}, "cursor"),
            ("self_nomad_proposal_list", {"extra_field": True}, "$"),
            (
                "self_nomad_intake_preview",
                {
                    "request": {
                        "schema_version": 99,
                        "request_id": "x",
                        "reason": "r",
                        "source": {"runtime": "a", "agent_identifier": "b"},
                        "operations": [
                            {
                                "kind": "replace",
                                "path": "memory/MEMORY.md",
                                "content": "# ok\n",
                            }
                        ],
                    }
                },
                "request.schema_version",
            ),
            (
                "self_nomad_intake_preview",
                {
                    "request": {
                        "schema_version": 1,
                        "request_id": "x",
                        "reason": "r",
                        "source": {"runtime": "a", "agent_identifier": "b"},
                        "operations": [
                            {
                                "kind": "replace",
                                "path": "memory/MEMORY.md",
                                "content": f"token {secret}\n",
                            }
                        ],
                        "extra_nested": 1,
                    }
                },
                "request",
            ),
            (
                "self_nomad_intake_preview",
                {
                    "request": {
                        "schema_version": 1,
                        "request_id": "x",
                        "reason": "r",
                        "source": {"runtime": "a", "agent_identifier": "b"},
                        "operations": [
                            {
                                "kind": "replace",
                                "path": "../escape.md",
                                "content": "# x\n",
                            }
                        ],
                    }
                },
                "request",
            ),
        ]

        for tool, args, path_hint in cases:
            result = await client.call_tool(tool, args)
            body = _body(result)
            text = "".join(
                getattr(block, "text", "") or "" for block in (result.content or [])
            )
            serialized = json.dumps(body) + text
            assert body["ok"] is False, (tool, args, body)
            assert body["schema_version"] == 1
            assert body["tool"] == tool
            assert body["result"] == {}
            assert body["errors"]
            assert body["errors"][0]["code"] == "MCP_INVALID_ARGUMENT"
            assert secret not in serialized
            assert "sk-live" not in serialized
            assert "input_value" not in serialized
            assert "validation error" not in serialized.lower()
            assert "not-a-uuid" not in serialized
            err_path = body["errors"][0].get("path")
            assert err_path == path_hint or (
                path_hint != "$" and err_path is not None and path_hint in err_path
            ), (tool, path_hint, err_path)

        # Malformed args must not create state.
        listed = await client.call_tool("self_nomad_proposal_list", {"limit": 50})
        assert _body(listed)["result"]["count"] == 0


async def test_sensitive_keys_never_appear_in_error_paths(tmp_path: Path) -> None:
    marker = "Bearer_sk-live-SECRET"
    async with _session(_repo(tmp_path)) as (client, _init):
        cases: list[tuple[str, dict[str, Any]]] = [
            ("self_nomad_proposal_list", {marker: True}),
            (
                "self_nomad_intake_preview",
                {
                    "request": {
                        "schema_version": 1,
                        "request_id": "x",
                        "reason": "r",
                        "source": {"runtime": "a", "agent_identifier": "b"},
                        "operations": [
                            {
                                "kind": "replace",
                                "path": "memory/MEMORY.md",
                                "content": "# ok\n",
                            }
                        ],
                        marker: True,
                    }
                },
            ),
            (
                "self_nomad_intake_preview",
                {
                    "request": {
                        "schema_version": 1,
                        "request_id": "x",
                        "reason": "r",
                        "source": {
                            "runtime": "a",
                            "agent_identifier": "b",
                            marker: True,
                        },
                        "operations": [
                            {
                                "kind": "replace",
                                "path": "memory/MEMORY.md",
                                "content": "# ok\n",
                            }
                        ],
                    }
                },
            ),
            (
                "self_nomad_intake_preview",
                {
                    "request": {
                        "schema_version": 1,
                        "request_id": "x",
                        "reason": "r",
                        "source": {"runtime": "a", "agent_identifier": "b"},
                        "operations": [
                            {
                                "kind": "replace",
                                "path": "memory/MEMORY.md",
                                "content": "# ok\n",
                                marker: True,
                            }
                        ],
                    }
                },
            ),
        ]
        for tool, args in cases:
            result = await client.call_tool(tool, args)
            body = _body(result)
            text = "".join(
                getattr(block, "text", "") or "" for block in (result.content or [])
            )
            serialized = json.dumps(body) + text
            assert body["ok"] is False
            assert body["errors"][0]["code"] == "MCP_INVALID_ARGUMENT"
            assert marker not in serialized
            assert "sk-live" not in serialized
            err_path = body["errors"][0].get("path") or ""
            assert marker not in err_path
        listed = await client.call_tool("self_nomad_proposal_list", {})
        assert _body(listed)["result"]["count"] == 0


async def test_invalid_request_with_sensitive_marker_no_state(tmp_path: Path) -> None:
    marker = "SECRET_MARKER_TOKEN=should-never-appear"
    async with _session(_repo(tmp_path)) as (client, _init):
        result = await client.call_tool(
            "self_nomad_intake_submit",
            {
                "request": {
                    "schema_version": 1,
                    "request_id": "mcp:secret:1",
                    "reason": "bad",
                    "source": {"runtime": "a", "agent_identifier": "b"},
                    "operations": [
                        {
                            "kind": "replace",
                            "path": "memory/MEMORY.md",
                            "content": f"# Memory\n\n{marker}\n",
                        }
                    ],
                    "not_allowed": True,
                }
            },
        )
        body = _body(result)
        assert body["ok"] is False
        assert marker not in json.dumps(body)
        listed = await client.call_tool("self_nomad_proposal_list", {})
        assert _body(listed)["result"]["count"] == 0


async def test_server_version_matches_package(tmp_path: Path) -> None:
    from self_nomad import __version__

    async with _session(_repo(tmp_path)) as (client, _init):
        # initialize already done; list tools to keep session busy
        tools = await client.list_tools()
        assert tools.tools
        status = await client.call_tool("self_nomad_repository_status", {})
        body = _body(status)
        assert body["result"]["package_version"] == __version__
