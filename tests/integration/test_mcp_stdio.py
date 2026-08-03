"""Stdio subprocess MCP client tests for self-nomad-mcp."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from self_nomad.application import SelfNomad
from self_nomad.mcp_server.tools import EXPECTED_TOOL_NAMES
from tests.helpers import configure_git_identity, run_git

pytest.importorskip("mcp")

pytestmark = pytest.mark.asyncio


def _repo(tmp_path: Path) -> Path:
    app = SelfNomad.initialize(tmp_path / "agent", name="mcp-stdio")
    configure_git_identity(app.repository.root)
    run_git(app.repository.root, "add", ".")
    run_git(app.repository.root, "commit", "-m", "initial")
    return app.repository.root.resolve()


def _server_command(repo: Path) -> list[str]:
    # Prefer the installed console script when available; fall back to module.
    return [
        sys.executable,
        "-m",
        "self_nomad.mcp_server.main",
        "--repo",
        str(repo),
    ]


async def test_stdio_startup_list_status_submit_shutdown(tmp_path: Path) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    root = _repo(tmp_path)
    params = StdioServerParameters(
        command=_server_command(root)[0],
        args=_server_command(root)[1:],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src")},
    )

    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as client,
    ):
        await client.initialize()
        tools = await client.list_tools()
        names = sorted(t.name for t in tools.tools)
        assert names == sorted(EXPECTED_TOOL_NAMES)

        status = await client.call_tool("self_nomad_repository_status", {})
        assert status.is_error is False
        assert status.structured_content["ok"] is True
        assert status.structured_content["result"]["repository"]["name"] == "mcp-stdio"

        request: dict[str, Any] = {
            "schema_version": 1,
            "request_id": "mcp:stdio:1",
            "reason": "Stdio MCP intake.",
            "source": {"runtime": "hermes", "agent_identifier": "cli"},
            "operations": [
                {
                    "kind": "replace",
                    "path": "memory/MEMORY.md",
                    "content": "# Memory\n\n- Stdio path works.\n",
                }
            ],
        }
        submitted = await client.call_tool(
            "self_nomad_intake_submit", {"request": request}
        )
        assert submitted.structured_content["ok"] is True
        proposal_id = submitted.structured_content["result"]["proposal_id"]

        got = await client.call_tool(
            "self_nomad_proposal_get", {"proposal_id": proposal_id}
        )
        assert got.structured_content["ok"] is True
        assert got.structured_content["result"]["proposal_id"] == proposal_id

        resources = await client.list_resources()
        assert any("proposal-request/v1" in str(r.uri) for r in resources.resources)


async def test_stdio_preview_zero_write(tmp_path: Path) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    root = _repo(tmp_path)
    state = tmp_path / "state"
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
        "XDG_STATE_HOME": str(state),
        "LOCALAPPDATA": str(state / "local"),
        "HOME": str(tmp_path / "home"),
        "USERPROFILE": str(tmp_path / "home"),
    }
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "self_nomad.mcp_server.main", "--repo", str(root)],
        env=env,
    )
    request = {
        "schema_version": 1,
        "request_id": "mcp:stdio-preview:1",
        "reason": "Preview only.",
        "source": {"runtime": "openclaw", "agent_identifier": "a"},
        "operations": [
            {
                "kind": "replace",
                "path": "memory/MEMORY.md",
                "content": "# Memory\n\n- preview\n",
            }
        ],
    }
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as client,
    ):
        await client.initialize()
        preview = await client.call_tool(
            "self_nomad_intake_preview", {"request": request}
        )
        assert preview.structured_content["ok"] is True
        listed = await client.call_tool("self_nomad_proposal_list", {})
        assert listed.structured_content["result"]["count"] == 0


async def test_main_rejects_relative_repo(tmp_path: Path) -> None:
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "self_nomad.mcp_server.main",
        "--repo",
        "relative/repo",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src")},
        cwd=str(tmp_path),
    )
    stdout, stderr = await proc.communicate()
    assert proc.returncode == 2
    assert b"absolute" in stderr.lower()
    # Protocol purity: no MCP JSON on stdout for startup failure.
    assert stdout.strip() == b""


async def test_stdio_missing_repo_stderr_only(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "self_nomad.mcp_server.main",
        "--repo",
        str(missing),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src")},
    )
    stdout, stderr = await proc.communicate()
    assert proc.returncode == 2
    assert stdout.strip() == b""
    assert b"error:" in stderr.lower() or b"error:" in stderr
