"""Textual pilot tests for the operator TUI. Drives SelfNomadApp, not a fake."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from textual.widgets import Input, Static
from typer.testing import CliRunner

from self_nomad.branding import TAGLINE, WORDMARK_LINES
from self_nomad.cli import app
from self_nomad.domain import ProposalStatus
from self_nomad.errors import ConflictError
from self_nomad.tui.app import SelfNomadApp
from self_nomad.tui.launch import MISSING_TUI_MESSAGE, is_missing_textual

runner = CliRunner()


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    state = tmp_path / "state"
    home.mkdir()
    state.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    monkeypatch.setenv("SELF_NOMAD_BANNER", "0")


def _repo(tmp_path: Path) -> Path:
    from self_nomad.application import SelfNomad

    root = tmp_path / "agent"
    SelfNomad.initialize(root, name="tui-agent", initialize_git=True)
    return root


def _text(pilot_app: SelfNomadApp, widget_id: str) -> str:
    widget = pilot_app.screen.query_one(widget_id, Static)
    return str(widget.render())


async def test_home_shows_wordmark_and_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch, tmp_path)
    root = _repo(tmp_path)
    application = SelfNomadApp(root)
    async with application.run_test(size=(100, 50)) as pilot:
        await pilot.pause()
        rendered = _text(application, "#wordmark") + _text(application, "#status")
    assert TAGLINE in rendered
    assert any(line in rendered for line in WORDMARK_LINES)
    assert application.gate.home_status()["digest"] in rendered
    assert "valid yes" in rendered


async def test_detect_lists_registered_adapters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch, tmp_path)
    root = _repo(tmp_path)
    application = SelfNomadApp(root)
    async with application.run_test(size=(100, 50)) as pilot:
        await pilot.press("f2")
        await pilot.pause()
        await pilot.click("#detect-run")
        await pilot.pause()
        body = _text(application, "#detect-body")
    assert "hermes:" in body
    assert "openclaw:" in body
    assert "agents-md:" in body


async def test_import_review_approve_apply_on_clean_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch, tmp_path)
    root = _repo(tmp_path)
    runtime = tmp_path / "hermes"
    runtime.mkdir()
    (runtime / "SOUL.md").write_text("# Soul\n\nImported persona.\n", encoding="utf-8")
    application = SelfNomadApp(root)
    async with application.run_test(size=(100, 50)) as pilot:
        await pilot.press("f3")
        await pilot.pause()
        await pilot.click("#import-adapter")
        application.screen.query_one("#import-adapter", Input).value = "hermes"
        application.screen.query_one("#import-path", Input).value = str(runtime)
        await pilot.click("#import-preview")
        await pilot.pause()
        preview = _text(application, "#message")
        assert "preview only" in preview
        assert application.gate.nomad.proposals().list_records() == []
        plan = _text(application, "#import-plan")
        assert "map" in plan
        assert "exclude" in plan
        await pilot.click("#import-confirm")
        await pilot.pause()
        records = application.gate.nomad.proposals().list_records()
        assert len(records) == 1
        assert records[0].status is not ProposalStatus.APPLIED
        await pilot.press("f4")
        await pilot.pause()
        await pilot.click("#review-diff")
        await pilot.pause()
        assert "persona" in _text(application, "#review-diff-body").lower() or "Soul" in _text(
            application, "#review-diff-body"
        )
        await pilot.click("#review-approve")
        await pilot.pause()
        assert "identifier is required" in _text(application, "#message")
        await pilot.click("#review-identifier")
        await pilot.press(*"operator")
        await pilot.pause()
        typed = application.screen.query_one("#review-identifier", Input).value
        assert typed == "operator", typed
        await pilot.click("#review-approve")
        await pilot.pause()
        approved = application.gate.nomad.proposals().list_records()[0]
        assert approved.status is ProposalStatus.APPROVED, _text(application, "#message")
        await pilot.press("f5")
        await pilot.pause()
        await pilot.click("#apply-run")
        await pilot.pause()
        applied = application.gate.nomad.proposals().list_records()[0]
        assert applied.status is ProposalStatus.APPLIED
        assert "Imported persona" in (root / "identity" / "persona.md").read_text(encoding="utf-8")


async def test_pack_check_install_omits_user_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch, tmp_path)
    root = _repo(tmp_path)
    archive = tmp_path / "agent.snpack"
    destination = tmp_path / "installed"
    application = SelfNomadApp(root)
    async with application.run_test(size=(100, 50)) as pilot:
        await pilot.press("f6")
        await pilot.pause()
        application.screen.query_one("#pack-out", Input).value = str(archive)
        await pilot.click("#pack-run")
        await pilot.pause()
        packed = _text(application, "#message")
        assert "specialist" in packed
        assert "user_profile" in packed
        await pilot.press("f7")
        await pilot.pause()
        application.screen.query_one("#check-archive", Input).value = str(archive)
        await pilot.click("#check-run")
        await pilot.pause()
        checked = _text(application, "#check-body")
        assert "specialist" in checked
        assert "user_profile" in checked
        application.screen.query_one("#install-dest", Input).value = str(destination)
        await pilot.click("#install-run")
        await pilot.pause()
    assert not (destination / "identity" / "user.md").exists()
    assert not (destination / "memory" / "daily").exists()
    assert (destination / "self-nomad.yaml").is_file()


def test_json_cli_does_not_launch_tui() -> None:
    result = runner.invoke(app, ["--json", "about"], catch_exceptions=False)
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "about"
    assert payload["result"]["tagline"] == TAGLINE
    assert "________" not in result.stdout


def test_tui_help_does_not_run_the_app() -> None:
    result = runner.invoke(app, ["tui", "--help"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "tui" in result.stdout.lower()


def test_missing_textual_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.util

    monkeypatch.setattr(importlib.util, "find_spec", lambda _name: None)
    absent = ModuleNotFoundError("No module named 'textual'")
    absent.name = "textual"
    assert is_missing_textual(absent)
    child = ModuleNotFoundError("No module named 'textual.app'")
    child.name = "textual.app"
    assert is_missing_textual(child)

    class _Spec:
        pass

    monkeypatch.setattr(importlib.util, "find_spec", lambda _name: _Spec())
    present = ModuleNotFoundError("No module named 'textual.app'")
    present.name = "textual.app"
    assert not is_missing_textual(present)
    other = ModuleNotFoundError("No module named 'self_nomad.tui'")
    other.name = "self_nomad.tui"
    assert not is_missing_textual(other)
    assert not is_missing_textual(ConflictError("no"))
    assert "self-nomad[tui]" in MISSING_TUI_MESSAGE


def test_core_dependencies_do_not_require_textual() -> None:
    import tomllib

    data = tomllib.loads(
        (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(encoding="utf-8")
    )
    core = data["project"]["dependencies"]
    assert not any("textual" in item for item in core)
    assert any("textual" in item for item in data["project"]["optional-dependencies"]["tui"])
