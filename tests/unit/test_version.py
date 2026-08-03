"""Version agreement across package interface, metadata, and CLI."""

from __future__ import annotations

import importlib.metadata
import re
import tomllib
from pathlib import Path

from typer.testing import CliRunner

from self_nomad import __version__
from self_nomad.cli import app

ROOT = Path(__file__).resolve().parents[2]


def project_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def test_public_version_matches_pyproject() -> None:
    expected = project_version()
    assert __version__ == expected
    assert re.fullmatch(r"[0-9].*", __version__)
    assert __version__ != "0+unknown"


def test_installed_package_metadata_matches_public_version() -> None:
    assert importlib.metadata.version("self-nomad") == project_version()
    assert importlib.metadata.version("self-nomad") == __version__


def test_cli_version_flag_matches_public_version() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == project_version()
    assert result.stdout.strip() == __version__


def test_source_tree_fallback_sentinel_is_unknown() -> None:
    """Uninstalled trees must not hard-code a release version string."""
    source = (ROOT / "src/self_nomad/__init__.py").read_text(encoding="utf-8")
    assert '"0+unknown"' in source
    assert "0.1.0rc1" not in source
