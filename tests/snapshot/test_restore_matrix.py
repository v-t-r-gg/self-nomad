"""Pack, install, and restore one specialist archive into Hermes and OpenClaw."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from self_nomad.cli import app
from self_nomad.domain import Fidelity

runner = CliRunner()


def _json(args: list[str]) -> dict[str, object]:
    result = runner.invoke(app, args, catch_exceptions=False)
    assert result.exit_code == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_specialist_pack_restores_exact_classes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    state = tmp_path / "state"
    home.mkdir()
    state.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    monkeypatch.setenv("USERPROFILE", str(home))

    repo = tmp_path / "agent"
    _json(
        [
            "--json",
            "init",
            str(repo),
            "--name",
            "demo-echo",
            "--description",
            "Echo specialist",
        ]
    )
    persona = "# Persona\n\nEcho answers with the words it was given.\n"
    instructions = "# Instructions\n\nRepeat the operator's last sentence.\n"
    identity = "# Identity\n\nName: Echo\n"
    notes = "# Tool notes\n\nNo tools.\n"
    skill = "---\nname: echo\ndescription: Repeat text.\n---\n\n# Echo\n"
    _replace(
        repo,
        tmp_path,
        {
            "identity/persona.md": persona,
            "identity/instructions.md": instructions,
            "identity/identity.md": identity,
            "tools/notes.md": notes,
            "skills/echo/SKILL.md": skill,
        },
    )
    archive = tmp_path / "demo-echo.snpack"
    packed = _json(["--json", "--repo", str(repo), "pack", "--out", str(archive)])
    result = packed["result"]
    assert isinstance(result, dict)
    assert result["profile"] == "specialist"
    installed = tmp_path / "installed"
    _json(["--json", "install", str(archive), "--to", str(installed), "--no-git"])
    assert not (installed / "identity" / "user.md").exists()
    assert not (installed / "memory" / "daily").exists()
    assert not (installed / "memory" / "MEMORY.md").exists()

    hermes = tmp_path / "hermes"
    openclaw = tmp_path / "openclaw"
    for adapter, target in (("hermes", hermes), ("openclaw", openclaw)):
        preview = _json(
            [
                "--json",
                "--repo",
                str(installed),
                "restore",
                "--adapter",
                adapter,
                "--to",
                str(target),
            ]
        )
        body = preview["result"]
        assert isinstance(body, dict)
        assert body["applied"] is False
        plan = body["plan"]
        assert isinstance(plan, dict)
        flagged = [
            item
            for item in [*_as_list(plan.get("mappings")), *_as_list(plan.get("exclusions"))]
            if isinstance(item, dict)
            and item.get("fidelity") in {Fidelity.ADAPTED.value, Fidelity.UNSUPPORTED.value}
        ]
        assert flagged, plan
        applied = _json(
            [
                "--json",
                "--repo",
                str(installed),
                "restore",
                "--adapter",
                adapter,
                "--to",
                str(target),
                "--yes",
            ]
        )
        applied_body = applied["result"]
        assert isinstance(applied_body, dict)
        assert applied_body["applied"] is True

    assert (hermes / "SOUL.md").read_text(encoding="utf-8") == persona
    assert (hermes / "skills" / "echo" / "SKILL.md").read_text(encoding="utf-8") == skill
    assert (openclaw / "SOUL.md").read_text(encoding="utf-8") == persona
    assert (openclaw / "IDENTITY.md").read_text(encoding="utf-8") == identity
    assert (openclaw / "TOOLS.md").read_text(encoding="utf-8") == notes
    assert (openclaw / "skills" / "echo" / "SKILL.md").read_text(encoding="utf-8") == skill
    assert (openclaw / "AGENTS.md").read_text(encoding="utf-8") == instructions


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _replace(repo: Path, work: Path, files: dict[str, str]) -> None:
    operations = []
    for relative, content in files.items():
        source = work / "src" / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(content, encoding="utf-8")
        kind = "replace" if (repo / relative).exists() else "add"
        operations.append(
            f"  - kind: {kind}\n    path: {relative}\n    content_source: {source.as_posix()}\n"
        )
    change = work / "change.yaml"
    change.write_text("operations:\n" + "".join(operations), encoding="utf-8")
    proposed = _json(
        [
            "--json",
            "--repo",
            str(repo),
            "propose",
            "--reason",
            "Seed specialist files",
            "--change",
            str(change),
        ]
    )
    proposal = proposed["result"]
    assert isinstance(proposal, dict)
    nested = proposal.get("proposal", proposal)
    assert isinstance(nested, dict)
    proposal_id = str(nested["id"])
    _json(["--json", "--repo", str(repo), "validate", proposal_id])
    _json(["--json", "--repo", str(repo), "approve", proposal_id, "--identifier", "operator"])
    applied = _json(["--json", "--repo", str(repo), "apply", proposal_id])
    body = applied["result"]
    assert isinstance(body, dict)
    status = body.get("status")
    if status is None and isinstance(body.get("proposal"), dict):
        status = body["proposal"].get("status")  # type: ignore[index]
    assert status == "applied"
