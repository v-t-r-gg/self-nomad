"""Unit tests for the bounded MCP tool surface."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import uuid4

import pytest

from self_nomad.application import SelfNomad
from self_nomad.domain import FileOperation, ProposalStatus
from self_nomad.errors import (
    GitOperationError,
    IntakeIdConflictError,
    IntakeSubmissionFailedError,
    IntakeTargetMovedError,
    ProposalNotFoundError,
    ProposalStaleError,
    ProposalStateError,
)
from self_nomad.mcp_server.errors import map_exception
from self_nomad.mcp_server.main import MISSING_MCP_MESSAGE, _is_missing_mcp_dependency, main
from self_nomad.mcp_server.sanitize import (
    decode_cursor,
    encode_cursor,
    sanitize_proposal,
    suggested_next_for_status,
)
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


def test_no_development_version_literal_in_mcp_server() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "self_nomad" / "mcp_server"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "0.2.0.dev0" not in text, f"version literal in {path}"


def test_status_does_not_create_state_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _repo(tmp_path)
    state = tmp_path / "isolated-state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    monkeypatch.setenv("LOCALAPPDATA", str(state / "local"))
    ctx = ToolContext(SelfNomad.open(app.repository.root))
    payload = ctx.status()
    assert payload["repository"]["name"] == "mcp-unit"
    assert "package_version" in payload
    assert payload["package_version"]  # from public version source
    assert payload["repository"]["root"] == str(app.repository.root.resolve())
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
    assert isinstance(sanitized["suggested_next"], list)
    assert sanitized["suggested_next"]
    assert all("channel" in step for step in sanitized["suggested_next"])


def test_suggested_next_capability_aware() -> None:
    mat = suggested_next_for_status(ProposalStatus.MATERIALIZED)
    assert any(
        step.get("channel") == "mcp" and step.get("tool") == "self_nomad_proposal_validate"
        for step in mat
    )
    assert any(
        step.get("channel") == "cli_operator" and "approve" in step.get("command", "")
        for step in mat
    )
    assert not any(
        step.get("channel") == "mcp" and "approve" in json.dumps(step) for step in mat
    )

    val = suggested_next_for_status(ProposalStatus.VALIDATED)
    assert all(step.get("channel") != "mcp" for step in val)
    assert any("approve" in step.get("command", "") for step in val)

    appr = suggested_next_for_status(ProposalStatus.APPROVED)
    assert len(appr) == 1
    assert appr[0]["channel"] == "cli_operator"
    assert "apply" in appr[0]["command"]

    assert suggested_next_for_status(ProposalStatus.APPLIED) == []
    assert suggested_next_for_status(ProposalStatus.REJECTED) == []
    assert suggested_next_for_status(ProposalStatus.STALE) == []
    assert suggested_next_for_status(ProposalStatus.FAILED) == []


def test_cursor_roundtrip() -> None:
    pid = uuid4()
    cursor = encode_cursor(pid)
    assert decode_cursor(cursor) == pid.hex
    with pytest.raises(ValueError):
        decode_cursor("%%%")


def test_map_exception_never_echoes_raw_details() -> None:
    path = "/tmp/staging/worktree/secret-branch"
    token = "Bearer sk-live-SUPERSECRET"
    git_stderr = f"fatal: not a git repository: {path}\n{token}\n"

    cases: list[BaseException] = [
        IntakeIdConflictError(f"conflict at {path} token={token}", code="INTAKE_ID_CONFLICT"),
        IntakeTargetMovedError(f"moved: {path}"),
        IntakeSubmissionFailedError(f"git failed: {git_stderr}"),
        ProposalNotFoundError(f"missing under {path}"),
        ProposalStaleError(f"stale tree {path}"),
        ProposalStateError(f"bad state near {path}"),
        GitOperationError(git_stderr),
        RuntimeError(f"boom {path}\n{token}\n{git_stderr}"),
    ]
    for exc in cases:
        code, message, _path = map_exception(exc)
        blob = json.dumps({"code": code, "message": message})
        assert path not in blob
        assert token not in blob
        assert "sk-live" not in blob
        assert "fatal:" not in blob
        assert "\n" not in message
        assert code
        assert message

    code, message, _ = map_exception(IntakeIdConflictError("x"))
    assert code == "INTAKE_ID_CONFLICT"
    assert message == "request_id was reused with a different payload"


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


def test_call_tool_maps_leaky_exceptions(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    app = _repo(tmp_path)
    ctx = ToolContext(app)
    leak = "/var/tmp/self-nomad/w/proposal-abc/secret.md"
    token = "Authorization: Bearer aabbccddeeff"

    def boom() -> dict[str, object]:
        raise GitOperationError(f"git stderr:\n{leak}\n{token}\n")

    with caplog.at_level(logging.ERROR, logger="self_nomad.mcp"):
        body = call_tool(ctx, "self_nomad_repository_status", boom)
    serialized = json.dumps(body)
    assert body["ok"] is False
    assert body["errors"][0]["code"] == "MCP_INTERNAL_ERROR"
    assert leak not in serialized
    assert token not in serialized
    assert "Bearer" not in serialized


def test_is_missing_mcp_dependency_classification() -> None:
    assert _is_missing_mcp_dependency(ImportError("No module named 'mcp'"))
    assert _is_missing_mcp_dependency(ImportError("No module named 'mcp.server'"))
    assert _is_missing_mcp_dependency(ImportError("No module named 'mcp_types'"))
    named = ImportError("No module named 'mcp'")
    named.name = "mcp"
    assert _is_missing_mcp_dependency(named)
    named_types = ImportError("No module named 'mcp_types'")
    named_types.name = "mcp_types"
    assert _is_missing_mcp_dependency(named_types)

    other = ImportError("No module named 'self_nomad.does_not_exist'")
    other.name = "self_nomad.does_not_exist"
    assert not _is_missing_mcp_dependency(other)
    assert not _is_missing_mcp_dependency(ImportError("circular import in self_nomad.mcp_server"))
    assert not _is_missing_mcp_dependency(ValueError("No module named 'mcp'"))
    assert "self-nomad[mcp]" in MISSING_MCP_MESSAGE


def test_main_requires_absolute_repo(tmp_path: Path) -> None:
    code = main(["--repo", "relative/path"])
    assert code == 2


def test_core_modules_import_without_server_binding() -> None:
    import importlib

    import self_nomad  # noqa: F401

    importlib.import_module("self_nomad.mcp_server.tools")
    importlib.import_module("self_nomad.mcp_server.models")
    importlib.import_module("self_nomad.mcp_server.errors")
    importlib.import_module("self_nomad.mcp_server.sanitize")
    importlib.import_module("self_nomad.cli")


def test_production_mcp_sources_avoid_private_sdk_members() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "self_nomad" / "mcp_server"
    banned = ("_tool_manager", "_resource_manager", "_lowlevel_server")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{path} references private SDK member {token}"
