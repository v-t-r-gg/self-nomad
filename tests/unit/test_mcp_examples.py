"""Static checks for published MCP host configuration examples."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from self_nomad.mcp_server.tools import EXPECTED_TOOL_NAMES

ROOT = Path(__file__).resolve().parents[2]
OPENCLAW = ROOT / "examples" / "mcp" / "openclaw.json5"
HERMES = ROOT / "examples" / "mcp" / "hermes.yaml"

# OpenClaw host-generated utilities (not native server tools).
OPENCLAW_RESOURCE_UTILS = ("resources_list", "resources_read")


def test_openclaw_example_lists_native_tools_and_resource_utils() -> None:
    text = OPENCLAW.read_text(encoding="utf-8")
    assert "mcp" in text
    assert "toolFilter" in text
    assert "self-nomad-mcp" in text
    assert "--repo" in text
    for name in EXPECTED_TOOL_NAMES:
        assert name in text
    for name in OPENCLAW_RESOURCE_UTILS:
        assert name in text
    # Host utilities must not be mistaken for native self_nomad tools.
    native = re.findall(r"self_nomad_[a-z_]+", text)
    assert sorted(set(native)) == sorted(EXPECTED_TOOL_NAMES)
    for forbidden in ("approve", "apply", "reject", "restore", "import", "cleanup"):
        assert f"self_nomad_{forbidden}" not in text


def test_openclaw_docs_probe_command() -> None:
    docs = (ROOT / "docs" / "mcp-openclaw.md").read_text(encoding="utf-8")
    assert "openclaw mcp doctor self_nomad --probe" in docs
    assert "resources_list" in docs
    assert "resources_read" in docs
    assert "Native tools" in docs or "native" in docs.lower()


def test_hermes_example_lists_exact_tools() -> None:
    text = HERMES.read_text(encoding="utf-8")
    assert "mcp_servers" in text
    assert "tools:" in text
    assert "include:" in text
    assert "prompts: false" in text
    assert "resources: true" in text
    assert "--repo" in text
    for name in EXPECTED_TOOL_NAMES:
        assert name in text
    listed = re.findall(r"self_nomad_[a-z_]+", text)
    assert sorted(set(listed)) == sorted(EXPECTED_TOOL_NAMES)


@pytest.mark.parametrize("path", [OPENCLAW, HERMES])
def test_examples_use_placeholder_absolute_paths(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "/absolute/path/" in text
