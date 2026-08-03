"""Version agreement across package interface, metadata, and CLI."""

from __future__ import annotations

import importlib.metadata
import re
import tomllib
from pathlib import Path

from typer.testing import CliRunner

from self_nomad import __version__
from self_nomad.cli import app

EXPECTED = "0.1.0rc1"
ROOT = Path(__file__).resolve().parents[2]


def test_public_version_is_release_candidate() -> None:
    assert __version__ == EXPECTED
    assert re.fullmatch(r"0\.1\.0rc1", __version__)


def test_pyproject_version_matches_public_version() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == EXPECTED
    assert data["project"]["version"] == __version__


def test_installed_package_metadata_matches_public_version() -> None:
    assert importlib.metadata.version("self-nomad") == EXPECTED
    assert importlib.metadata.version("self-nomad") == __version__


def test_cli_version_flag_matches_public_version() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == EXPECTED
