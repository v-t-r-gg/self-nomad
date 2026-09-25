"""Headless GUI tests. No display. The handler calls SelfNomad."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from self_nomad.branding import WORDMARK_LINES
from self_nomad.cli import app
from self_nomad.gui.app import GuiApp

runner = CliRunner()


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    state = tmp_path / "state"
    home.mkdir()
    state.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    monkeypatch.setenv("NO_COLOR", "1")


def _repo(tmp_path: Path) -> Path:
    from self_nomad.application import SelfNomad

    root = tmp_path / "agent"
    SelfNomad.initialize(root, name="gui-agent", initialize_git=True)
    return root


def test_status_page_shows_wordmark_and_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch, tmp_path)
    root = _repo(tmp_path)
    page = GuiApp(root).handle("GET", "/")
    assert "untethered from its runtime" in page
    assert any(line in page for line in WORDMARK_LINES)
    assert GuiApp(root).gate.home_status()["digest"] in page


def test_pack_and_install_omit_user_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch, tmp_path)
    root = _repo(tmp_path)
    archive = tmp_path / "agent.snpack"
    destination = tmp_path / "installed"
    gui = GuiApp(root)
    packed = gui.handle("POST", "/pack", {"profile": "specialist", "out": str(archive)})
    assert "specialist" in packed
    assert "user_profile" in packed
    checked = gui.handle("POST", "/check", {"action": "check", "archive": str(archive)})
    assert "user_profile" in checked
    installed = gui.handle(
        "POST",
        "/check",
        {"action": "install", "archive": str(archive), "dest": str(destination)},
    )
    assert "installed" in installed
    assert not (destination / "identity" / "user.md").exists()
    assert (destination / "self-nomad.yaml").is_file()


def test_review_requires_identifier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate(monkeypatch, tmp_path)
    root = _repo(tmp_path)
    runtime = tmp_path / "hermes"
    runtime.mkdir()
    (runtime / "SOUL.md").write_text("# Soul\n\nFrom GUI.\n", encoding="utf-8")
    gui = GuiApp(root)
    preview = gui.handle(
        "POST",
        "/import",
        {"action": "preview", "adapter": "hermes", "path": str(runtime)},
    )
    assert "preview only" in preview
    assert gui.gate.nomad.proposals().list_records() == []
    created = gui.handle("POST", "/import", {"action": "confirm"})
    records = gui.gate.nomad.proposals().list_records()
    assert len(records) == 1
    assert "applied" not in created
    proposal = str(records[0].proposal.id)
    refused = gui.handle(
        "POST",
        "/review",
        {"action": "approve", "proposal": proposal, "identifier": ""},
    )
    assert "identifier is required" in refused
    diff = gui.handle("POST", "/review", {"action": "diff", "proposal": proposal})
    assert "Soul" in diff or "persona" in diff.lower()


def test_json_does_not_open_gui() -> None:
    result = runner.invoke(app, ["--json", "gui"], catch_exceptions=False)
    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "does not open the GUI" in payload["errors"][0]


def test_gui_extra_does_not_pull_a_toolkit() -> None:
    import tomllib

    data = tomllib.loads(
        (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert data["project"]["optional-dependencies"]["gui"] == []
    assert not any("tkinter" in item or "PyQt" in item for item in data["project"]["dependencies"])
