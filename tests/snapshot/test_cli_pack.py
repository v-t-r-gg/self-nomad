"""CLI pack --check JSON is stable and indexer-shaped."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from self_nomad import __version__
from self_nomad.application import SelfNomad
from self_nomad.cli import app

runner = CliRunner()


def test_pack_check_json_is_stable_and_indexed(tmp_path: Path) -> None:
    repo = tmp_path / "agent"
    app_obj = SelfNomad.initialize(repo, name="indexer", description="Index me")
    skill = repo / "skills" / "echo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: echo\ndescription: Repeat.\n---\n\n# Echo\n",
        encoding="utf-8",
    )
    archive = tmp_path / "indexer.snpack"
    summary = app_obj.pack(archive)
    first = _check(archive)
    second = _check(archive)
    assert first == second
    result = first["result"]
    assert isinstance(result, dict)
    assert result["profile"] == "specialist"
    assert "user_profile" in result["omitted"]
    assert "daily_memory" in result["omitted"]
    assert result["content_digest"] == summary.content_digest
    assert result["skills"] == ["echo"]
    assert result["packer_version"] == __version__
    listed = runner.invoke(
        app,
        ["--json", "pack", "--list", str(archive)],
        catch_exceptions=False,
    )
    assert listed.exit_code == 0, listed.stdout
    payload = json.loads(listed.stdout)
    assert payload["result"]["members"]
    assert "self-nomad.pack.json" in payload["result"]["members"]


def _check(archive: Path) -> dict[str, object]:
    completed = runner.invoke(
        app,
        ["--json", "pack", "--check", str(archive)],
        catch_exceptions=False,
    )
    assert completed.exit_code == 0, completed.stdout + completed.stderr
    return json.loads(completed.stdout)
