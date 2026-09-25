"""Unit tests for documentation checker helpers."""

from __future__ import annotations

from pathlib import Path

from scripts.check_docs import (
    cli_commands,
    expected_mcp_tools,
    project_version,
    resolve_link,
)


def test_project_version_reads_pyproject() -> None:
    version = project_version()
    assert version  # non-empty
    assert version[0].isdigit()


def test_cli_commands_include_core_set() -> None:
    cmds = cli_commands()
    for name in (
        "init",
        "validate",
        "status",
        "propose",
        "review",
        "proposals",
        "log",
        "approve",
        "apply",
        "reject",
        "detect",
        "diff",
        "import",
        "restore",
        "intake",
        "about",
        "pack",
        "install",
    ):
        assert name in cmds


def test_expected_mcp_tools_are_seven() -> None:
    tools = expected_mcp_tools()
    assert len(tools) == 7
    assert all(t.startswith("self_nomad_") for t in tools)


def test_resolve_link_external_and_anchor() -> None:
    src = Path(__file__).resolve()
    assert resolve_link(src, "https://example.com/x") is None
    assert resolve_link(src, "#section") is None


def test_resolve_link_relative(tmp_path: Path) -> None:
    doc = tmp_path / "doc.md"
    target = tmp_path / "other.md"
    target.write_text("x\n", encoding="utf-8")
    doc.write_text("[t](other.md)\n", encoding="utf-8")
    resolved = resolve_link(doc, "other.md")
    assert resolved is not None
    assert resolved.is_file()
