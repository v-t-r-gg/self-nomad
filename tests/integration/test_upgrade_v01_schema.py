"""Current tooling must accept a frozen first-RC schema 1 repository."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from self_nomad.application import SelfNomad
from self_nomad.cli import app
from tests.helpers import configure_git_identity, run_git

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "upgrade" / "v0_1_schema1"
runner = CliRunner()


def _copy_fixture(tmp_path: Path) -> Path:
    dest = tmp_path / "v01"
    shutil.copytree(FIXTURE, dest)
    run_git(dest, "init", "--initial-branch=main")
    configure_git_identity(dest)
    run_git(dest, "add", ".")
    run_git(dest, "commit", "-m", "frozen first-rc tree")
    return dest


def test_v01_schema_fixture_validates_strict(isolated_env: Path, tmp_path: Path) -> None:
    dest = _copy_fixture(tmp_path)
    result = SelfNomad.open(dest).repository.validate(strict=True)
    assert result.valid is True
    assert result.findings == []
    policy = dest / "policy" / "policy.yaml"
    assert "maximum_request_bytes" not in policy.read_text(encoding="utf-8")


def test_v01_schema_fixture_accepts_proposal_lifecycle(
    isolated_env: Path, tmp_path: Path
) -> None:
    dest = _copy_fixture(tmp_path)
    source = tmp_path / "memory.md"
    source.write_text("# Memory\n\n- Upgraded operator still works.\n", encoding="utf-8")
    change = tmp_path / "change.yaml"
    change.write_text(
        "operations:\n"
        "  - kind: replace\n"
        "    path: memory/MEMORY.md\n"
        f"    content_source: {source.as_posix()}\n",
        encoding="utf-8",
    )
    proposed = runner.invoke(
        app,
        [
            "--repo",
            str(dest),
            "--json",
            "propose",
            "--reason",
            "Upgrade-path memory update",
            "--change",
            str(change),
        ],
        catch_exceptions=False,
    )
    assert proposed.exit_code == 0, proposed.stdout + proposed.stderr
    payload = json.loads(proposed.stdout)
    proposal_id = payload["result"]["proposal"]["id"]
    validated = runner.invoke(
        app, ["--repo", str(dest), "--json", "validate", proposal_id], catch_exceptions=False
    )
    assert validated.exit_code == 0, validated.stdout
    approved = runner.invoke(
        app,
        ["--repo", str(dest), "--json", "approve", proposal_id, "--identifier", "operator"],
        catch_exceptions=False,
    )
    assert approved.exit_code == 0, approved.stdout
    applied = runner.invoke(
        app, ["--repo", str(dest), "--json", "apply", proposal_id], catch_exceptions=False
    )
    assert applied.exit_code == 0, applied.stdout + applied.stderr
    assert "Upgraded operator still works" in (dest / "memory" / "MEMORY.md").read_text(
        encoding="utf-8"
    )
