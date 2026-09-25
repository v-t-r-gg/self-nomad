#!/usr/bin/env python3
"""Deterministic documentation consistency checks (network-free).

Verifies:

* Relative Markdown links resolve to existing files
* Referenced local files exist
* No hard-coded current project version outside historical contexts
* Documented CLI command names exist in the Typer registry
* Documented native MCP tool names match EXPECTED_TOOL_NAMES
* Packaged and docs ProposalRequest schemas are identical
* Examples referenced under examples/ exist

Usage::

    uv run python scripts/check_docs.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DOCS = ROOT / "docs"
EXAMPLES = ROOT / "examples"

# Files scanned for Markdown links and command references.
DOC_GLOBS = [
    "README.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "docs/**/*.md",
    "examples/**/*.md",
]

# Historical version mentions are allowed in these paths.
HISTORICAL_VERSION_ALLOW = {
    "CHANGELOG.md",
    "docs/upgrading.md",
    "docs/decisions",
    "docs/releases",
}

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
CLI_CMD_RE = re.compile(r"`self-nomad\s+([a-z][a-z0-9-]*)`")
MCP_TOOL_RE = re.compile(r"`(self_nomad_[a-z_]+)`")
# 0.x.y only. Do not treat an IPv4 octet run (127.0.0.1) as a version.
VERSION_RE = re.compile(r"(?<!\d\.)\b0\.\d+\.\d+(?:\.dev\d+|rc\d+)?\b(?!\.\d)")


def _iter_doc_files() -> list[Path]:
    files: list[Path] = []
    for pattern in DOC_GLOBS:
        files.extend(ROOT.glob(pattern))
    # de-dupe, skip caches
    unique = sorted({p.resolve() for p in files if p.is_file()})
    return [p for p in unique if ".pytest_cache" not in p.parts]


def project_version() -> str:
    import tomllib

    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def cli_commands() -> set[str]:
    # Import without requiring MCP extra.
    sys.path.insert(0, str(SRC))
    from typer.main import get_command

    from self_nomad.cli import app

    cmd = get_command(app)
    return set(cmd.list_commands(None))  # type: ignore[arg-type]


def expected_mcp_tools() -> tuple[str, ...]:
    sys.path.insert(0, str(SRC))
    from self_nomad.mcp_server.tools import EXPECTED_TOOL_NAMES

    return EXPECTED_TOOL_NAMES


def resolve_link(source: Path, target: str) -> Path | None:
    if target.startswith(("http://", "https://", "mailto:", "#")):
        return None
    # strip anchors and titles
    path_part = target.split("#", 1)[0].strip()
    if not path_part:
        return None
    if path_part.startswith("<") and path_part.endswith(">"):
        path_part = path_part[1:-1]
    # ignore pure query / empty
    if not path_part or path_part.startswith("?"):
        return None
    candidate = (source.parent / path_part).resolve()
    return candidate


def check_links(files: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            raw = match.group(1).strip().strip("\"'")
            # Markdown image/link with title: url "title"
            raw = raw.split()[0] if raw else raw
            resolved = resolve_link(path, raw)
            if resolved is None:
                continue
            if not resolved.exists():
                rel = path.relative_to(ROOT)
                errors.append(f"{rel}: broken link -> {raw}")
    return errors


def check_versions(files: list[Path], current: str) -> list[str]:
    errors: list[str] = []
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        if any(rel == a or rel.startswith(a.rstrip("/") + "/") for a in HISTORICAL_VERSION_ALLOW):
            continue
        text = path.read_text(encoding="utf-8")
        for match in VERSION_RE.finditer(text):
            found = match.group(0)
            # Allow the single current project version string for status language.
            if found == current:
                continue
            # Allow Python version triples like 3.11 only matched partially — VERSION_RE is 0.x
            if found.startswith("0.") and found != current:
                # rc / historical only allowed in allowlist paths
                errors.append(f"{rel}: unexpected version literal {found!r}")
    return errors


def check_cli_commands(files: list[Path], commands: set[str]) -> list[str]:
    errors: list[str] = []
    documented: set[str] = set()
    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in CLI_CMD_RE.finditer(text):
            name = match.group(1)
            documented.add(name)
            if name not in commands and name not in {
                "mcp",  # not a CLI subcommand of self-nomad
            }:
                # self-nomad-mcp is a separate entry point
                if name == "nomad-mcp":
                    continue
                errors.append(
                    f"{path.relative_to(ROOT)}: unknown CLI command `self-nomad {name}`"
                )
    # self-nomad-mcp is not matched by CLI_CMD_RE — fine
    return errors


def check_mcp_tools(files: list[Path], expected: tuple[str, ...]) -> list[str]:
    errors: list[str] = []
    expected_set = set(expected)
    for path in files:
        text = path.read_text(encoding="utf-8")
        if "self_nomad_" not in text:
            continue
        found = set(MCP_TOOL_RE.findall(text))
        # Only enforce on docs that claim the registry / allow-list
        claims_registry = (
            "EXPECTED" in text
            or "allow-list" in text
            or "native tool" in text.lower()
            or path.name == "mcp.md"
        )
        if claims_registry:
            unknown = {
                t for t in found if t.startswith("self_nomad_") and t not in expected_set
            }
            for bad in ("self_nomad_approve", "self_nomad_apply", "self_nomad_reject"):
                if bad in found:
                    errors.append(f"{path.relative_to(ROOT)}: forbidden tool name {bad}")
            for name in unknown:
                if name.endswith(("_approve", "_apply", "_reject", "_restore", "_import")):
                    errors.append(
                        f"{path.relative_to(ROOT)}: forbidden tool fragment {name}"
                    )
    # Ensure mcp.md lists all seven
    mcp_doc = DOCS / "mcp.md"
    if mcp_doc.is_file():
        text = mcp_doc.read_text(encoding="utf-8")
        for name in expected:
            if name not in text:
                errors.append(f"docs/mcp.md: missing native tool {name}")
    return errors


def check_schemas() -> list[str]:
    errors: list[str] = []
    pairs = (
        (
            "ProposalRequest",
            SRC / "self_nomad" / "schemas" / "proposal-request-v1.schema.json",
            DOCS / "schema" / "proposal-request-v1.schema.json",
        ),
        (
            "pack sidecar",
            SRC / "self_nomad" / "schemas" / "self-nomad-pack-v1.schema.json",
            DOCS / "schema" / "self-nomad-pack-v1.schema.json",
        ),
    )
    for label, packaged, docs_copy in pairs:
        if not packaged.is_file():
            errors.append(f"missing packaged schema: {packaged.relative_to(ROOT)}")
            continue
        if not docs_copy.is_file():
            errors.append(f"missing docs schema: {docs_copy.relative_to(ROOT)}")
            continue
        if packaged.read_bytes() != docs_copy.read_bytes():
            errors.append(f"packaged and docs {label} schemas differ")
    return errors


def check_examples() -> list[str]:
    errors: list[str] = []
    required = [
        EXAMPLES / "intake" / "hermes-memory-update.json",
        EXAMPLES / "intake" / "openclaw-memory-update.json",
        EXAMPLES / "intake" / "skill-addition.json",
        EXAMPLES / "mcp" / "openclaw.json5",
        EXAMPLES / "mcp" / "hermes.yaml",
        EXAMPLES / "e2e" / "README.md",
        EXAMPLES / "e2e" / "request.json",
    ]
    for path in required:
        if not path.is_file():
            errors.append(f"missing example: {path.relative_to(ROOT)}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    files = _iter_doc_files()
    errors: list[str] = []
    errors.extend(check_links(files))
    current = project_version()
    errors.extend(check_versions(files, current))
    try:
        commands = cli_commands()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: cannot load CLI: {exc}", file=sys.stderr)
        return 2
    errors.extend(check_cli_commands(files, commands))
    try:
        tools = expected_mcp_tools()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: cannot load MCP tools: {exc}", file=sys.stderr)
        return 2
    errors.extend(check_mcp_tools(files, tools))
    errors.extend(check_schemas())
    errors.extend(check_examples())

    if errors:
        print(f"{len(errors)} documentation check failure(s):", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(f"Documentation checks OK ({len(files)} files, version={current}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
