"""Unit tests for the bounded MCP tool surface."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import uuid4

import pytest

from self_nomad.application import SelfNomad
from self_nomad.domain import FileOperation
from self_nomad.errors import IntakeIdConflictError
from self_nomad.mcp_server.errors import map_exception
from self_nomad.mcp_server.sanitize import decode_cursor, encode_cursor, sanitize_proposal
from self_nomad.mcp_server.tools import (
    EXPECTED_TOOL_NAMES,
    FORBIDDEN_TOOL_SUBSTRINGS,
    ToolContext,
    call_tool,
    envelope,
)
from tests.helpers import configure_git_identity, run_git

pytest.importorskip("mcp")


def _repo(tmp_path: Path) -> SelfNomad:
    app = SelfNomad.initialize(tmp_path / "agent", name="mcp-unit")
    configure_git_identity(app.repository.root)
    run_git(app.repository.root, "add", ".")
    run_git(app.repository.root, "commit", "-m", "initial")
    return app


def test_expected_tool_names_are_closed_and_ordered() -> None:
    assert len(EXPECTED_TOOL_NAMES) == 7
    assert EXPECTED_TOOL_NAMES == (
        "self_nomad_repository_status",
        "self_nomad_repository_validate",
        "self_nomad_intake_preview",
        "self_nomad_intake_submit",
        "self_nomad_proposal_list",
        "self_nomad_proposal_get",
        "self_nomad_proposal_validate",
    )
    for name in EXPECTED_TOOL_NAMES:
        assert name.startswith("self_nomad_")
    for forbidden in FORBIDDEN_TOOL_SUBSTRINGS:
        assert not any(
            forbidden == part for name in EXPECTED_TOOL_NAMES for part in name.split("_")
        )


def test_build_server_registers_exact_tool_set(tmp_path: Path) -> None:
    from self_nomad.mcp_server.server import build_server

    app = _repo(tmp_path)
    server = build_server(app.repository.root)
    tools = list(server._tool_manager.list_tools())  # noqa: SLF001
    names = sorted(tool.name for tool in tools)
    assert names == sorted(EXPECTED_TOOL_NAMES)
    by_name = {tool.name: tool for tool in tools}

    assert by_name["self_nomad_repository_status"].annotations.read_only_hint is True
    assert by_name["self_nomad_repository_status"].annotations.destructive_hint is False
    assert by_name["self_nomad_repository_status"].annotations.idempotent_hint is True
    assert by_name["self_nomad_repository_status"].annotations.open_world_hint is False

    assert by_name["self_nomad_intake_submit"].annotations.read_only_hint is False
    assert by_name["self_nomad_intake_submit"].annotations.destructive_hint is False
    assert by_name["self_nomad_intake_submit"].annotations.idempotent_hint is True
    assert by_name["self_nomad_intake_submit"].annotations.open_world_hint is False

    assert by_name["self_nomad_proposal_validate"].annotations.read_only_hint is False
    assert by_name["self_nomad_proposal_validate"].annotations.idempotent_hint is True

    for tool in tools:
        assert tool.annotations is not None
        assert tool.annotations.open_world_hint is False
        assert tool.annotations.destructive_hint is False


def test_tool_input_schemas_are_flat_where_documented(tmp_path: Path) -> None:
    from self_nomad.mcp_server.server import build_server

    app = _repo(tmp_path)
    server = build_server(app.repository.root)
    by_name = {tool.name: tool for tool in server._tool_manager.list_tools()}  # noqa: SLF001

    assert by_name["self_nomad_repository_status"].parameters["properties"] == {}
    validate_props = by_name["self_nomad_repository_validate"].parameters["properties"]
    assert "strict" in validate_props
    assert "payload" not in validate_props

    list_props = by_name["self_nomad_proposal_list"].parameters["properties"]
    assert set(list_props) >= {"status", "limit", "cursor"}

    get_props = by_name["self_nomad_proposal_get"].parameters["properties"]
    assert "proposal_id" in get_props
    assert "payload" not in get_props

    preview_props = by_name["self_nomad_intake_preview"].parameters["properties"]
    assert "request" in preview_props


def test_status_does_not_create_state_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _repo(tmp_path)
    state = tmp_path / "isolated-state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    monkeypatch.setenv("LOCALAPPDATA", str(state / "local"))
    ctx = ToolContext(SelfNomad.open(app.repository.root))
    payload = ctx.status()
    assert payload["repository"]["name"] == "mcp-unit"
    assert "package_version" in payload
    assert payload["repository"]["root"] == str(app.repository.root.resolve())
    # Status listing must not create proposal state trees.
    assert not any(state.rglob("*.json"))


def test_sanitize_proposal_omits_content_source(tmp_path: Path) -> None:
    app = _repo(tmp_path)
    source = tmp_path / "m.md"
    source.write_text("# Memory\n\nx\n", encoding="utf-8")
    record = app.proposals(state_root=tmp_path / "s").create(
        reason="r",
        operations=[
            FileOperation(kind="replace", path="memory/MEMORY.md", content_source=str(source))
        ],
    )
    sanitized = sanitize_proposal(record)
    blob = json.dumps(sanitized)
    assert "content_source" not in blob
    assert str(tmp_path) not in blob
    assert sanitized["operations"][0]["path"] == "memory/MEMORY.md"
    assert "suggested_next" in sanitized


def test_cursor_roundtrip() -> None:
    pid = uuid4()
    cursor = encode_cursor(pid)
    assert decode_cursor(cursor) == pid.hex
    with pytest.raises(ValueError):
        decode_cursor("%%%")
    with pytest.raises(ValueError):
        decode_cursor(encode_cursor(pid)[:-2] + "!!")


def test_map_exception_codes() -> None:
    code, message = map_exception(IntakeIdConflictError("x", code="INTAKE_ID_CONFLICT"))
    assert code == "INTAKE_ID_CONFLICT"
    assert "x" in message
    code2, msg2 = map_exception(RuntimeError("boom secret=/etc/passwd"))
    assert code2 == "MCP_INTERNAL_ERROR"
    assert "boom" not in msg2
    assert "/etc" not in msg2


def test_envelope_shape() -> None:
    body = envelope("self_nomad_repository_status", ok=True, result={"x": 1})
    assert body == {
        "schema_version": 1,
        "tool": "self_nomad_repository_status",
        "ok": True,
        "result": {"x": 1},
        "warnings": [],
        "errors": [],
    }


def test_call_tool_maps_unexpected_without_traceback(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    app = _repo(tmp_path)
    ctx = ToolContext(app)

    def boom() -> dict[str, object]:
        raise RuntimeError("trace me /secret/path")

    with caplog.at_level(logging.ERROR, logger="self_nomad.mcp"):
        body = call_tool(ctx, "self_nomad_repository_status", boom)
    assert body["ok"] is False
    assert body["errors"][0]["code"] == "MCP_INTERNAL_ERROR"
    assert "trace me" not in json.dumps(body)
    assert any("internal error" in record.message for record in caplog.records)


def test_schema_resource_registered(tmp_path: Path) -> None:
    from importlib.resources import files

    from self_nomad.mcp_server.server import build_server

    app = _repo(tmp_path)
    server = build_server(app.repository.root)
    resources = server._resource_manager.list_resources()  # noqa: SLF001
    uris = [str(r.uri) for r in resources]
    assert "self-nomad://schemas/proposal-request/v1" in uris
    packaged = files("self_nomad.schemas").joinpath("proposal-request-v1.schema.json").read_text()
    assert "schema_version" in packaged


def test_open_fixed_repository_rejects_missing(tmp_path: Path) -> None:
    from self_nomad.mcp_server.errors import McpRepositoryUnavailableError
    from self_nomad.mcp_server.server import open_fixed_repository

    with pytest.raises(McpRepositoryUnavailableError):
        open_fixed_repository(tmp_path / "missing")
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(McpRepositoryUnavailableError):
        open_fixed_repository(empty)


def test_main_requires_absolute_repo(tmp_path: Path) -> None:
    from self_nomad.mcp_server.main import main

    code = main(["--repo", "relative/path"])
    assert code == 2


def test_optional_dependency_error_message() -> None:
    from self_nomad.mcp_server.errors import McpConfigurationError

    err = McpConfigurationError(
        "the MCP surface requires the optional dependency; "
        "install with: pip install 'self-nomad[mcp]'"
    )
    assert "self-nomad[mcp]" in str(err)


def test_core_modules_import_without_server_binding() -> None:
    """Tools/models/errors must not require constructing an MCPServer."""
    import importlib

    import self_nomad  # noqa: F401

    importlib.import_module("self_nomad.mcp_server.tools")
    importlib.import_module("self_nomad.mcp_server.models")
    importlib.import_module("self_nomad.mcp_server.errors")
    importlib.import_module("self_nomad.mcp_server.sanitize")
    importlib.import_module("self_nomad.cli")
