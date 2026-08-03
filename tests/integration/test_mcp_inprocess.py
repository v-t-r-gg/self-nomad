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


def _request(request_id: str = "mcp:memory:1") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "request_id": request_id,
        "reason": "Record a preference via MCP.",
        "source": {"runtime": "openclaw", "agent_identifier": "primary"},
        "operations": [
            {
                "kind": "replace",
                "path": "memory/MEMORY.md",
                "content": "# Memory\n\n- Prefers MCP intake.\n",
            }
        ],
    }


@asynccontextmanager
async def _session(root: Path) -> AsyncIterator[Any]:
    from mcp import ClientSession
    from mcp.client._memory import InMemoryTransport

    server = build_server(root)
    async with (
        InMemoryTransport(server, raise_exceptions=True) as (read, write),
        ClientSession(read, write) as client,
    ):
        await client.initialize()
        yield client


async def test_tool_discovery_exact_set(tmp_path: Path) -> None:
    async with _session(_repo(tmp_path)) as client:
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


async def test_repository_status_and_validate(tmp_path: Path) -> None:
    async with _session(_repo(tmp_path)) as client:
        status = await client.call_tool("self_nomad_repository_status", {})
        assert status.is_error is False
        body = status.structured_content
        assert body is not None
        assert body["ok"] is True
        assert body["schema_version"] == 1
        assert body["tool"] == "self_nomad_repository_status"
        assert body["result"]["repository"]["name"] == "mcp-inproc"
        assert body["result"]["proposals"]["total"] == 0

        validated = await client.call_tool(
            "self_nomad_repository_validate", {"strict": True}
        )
        assert validated.is_error is False
        assert validated.structured_content["ok"] is True
        assert validated.structured_content["result"]["valid"] is True


async def test_intake_preview_submit_list_get_validate(tmp_path: Path) -> None:
    async with _session(_repo(tmp_path)) as client:
        request = _request()

        preview = await client.call_tool(
            "self_nomad_intake_preview", {"request": request}
        )
        assert preview.is_error is False
        assert preview.structured_content["ok"] is True
        assert preview.structured_content["result"]["eligible"] is True
        assert "Prefers MCP" not in json.dumps(preview.structured_content)

        submitted = await client.call_tool(
            "self_nomad_intake_submit", {"request": request}
        )
        assert submitted.is_error is False
        assert submitted.structured_content["ok"] is True
        proposal_id = submitted.structured_content["result"]["proposal_id"]
        assert submitted.structured_content["result"]["reused"] is False

        again = await client.call_tool(
            "self_nomad_intake_submit", {"request": request}
        )
        assert again.structured_content["result"]["reused"] is True
        assert again.structured_content["result"]["proposal_id"] == proposal_id

        listed = await client.call_tool(
            "self_nomad_proposal_list", {"limit": 10, "status": "materialized"}
        )
        assert listed.structured_content["ok"] is True
        assert listed.structured_content["result"]["count"] >= 1

        got = await client.call_tool(
            "self_nomad_proposal_get", {"proposal_id": proposal_id}
        )
        assert got.structured_content["ok"] is True
        assert got.structured_content["result"]["proposal_id"] == proposal_id
        assert "content_source" not in json.dumps(got.structured_content)
        assert got.structured_content["result"]["status"] == "materialized"

        validated = await client.call_tool(
            "self_nomad_proposal_validate", {"proposal_id": proposal_id}
        )
        assert validated.structured_content["ok"] is True
        assert validated.structured_content["result"]["status"] == "validated"

        again_val = await client.call_tool(
            "self_nomad_proposal_validate", {"proposal_id": proposal_id}
        )
        assert again_val.structured_content["ok"] is True
        assert again_val.structured_content["result"]["status"] == "validated"


async def test_schema_resource(tmp_path: Path) -> None:
    async with _session(_repo(tmp_path)) as client:
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
    async with _session(_repo(tmp_path)) as client:
        missing = str(uuid4())
        got = await client.call_tool(
            "self_nomad_proposal_get", {"proposal_id": missing}
        )
        assert got.is_error is False
        assert got.structured_content["ok"] is False
        assert got.structured_content["errors"][0]["code"] == "PROPOSAL_NOT_FOUND"


async def test_concurrent_identical_submissions(tmp_path: Path) -> None:
    request = _request("mcp:concurrent:1")
    async with _session(_repo(tmp_path)) as client:
        results = await asyncio.gather(
            client.call_tool("self_nomad_intake_submit", {"request": request}),
            client.call_tool("self_nomad_intake_submit", {"request": request}),
        )
    bodies = [r.structured_content for r in results]
    assert all(b["ok"] for b in bodies)
    ids = {b["result"]["proposal_id"] for b in bodies}
    assert len(ids) == 1


async def test_preview_does_not_create_proposals(tmp_path: Path) -> None:
    async with _session(_repo(tmp_path)) as client:
        request = _request("mcp:preview-only:1")
        preview = await client.call_tool(
            "self_nomad_intake_preview", {"request": request}
        )
        assert preview.structured_content["ok"] is True
        listed = await client.call_tool("self_nomad_proposal_list", {"limit": 50})
        assert listed.structured_content["result"]["count"] == 0


async def test_id_conflict_error(tmp_path: Path) -> None:
    async with _session(_repo(tmp_path)) as client:
        request = _request("mcp:conflict:1")
        first = await client.call_tool(
            "self_nomad_intake_submit", {"request": request}
        )
        assert first.structured_content["ok"] is True
        conflicted = dict(request)
        conflicted["reason"] = "Different payload same request_id"
        second = await client.call_tool(
            "self_nomad_intake_submit", {"request": conflicted}
        )
        assert second.structured_content["ok"] is False
        assert second.structured_content["errors"][0]["code"] == "INTAKE_ID_CONFLICT"
