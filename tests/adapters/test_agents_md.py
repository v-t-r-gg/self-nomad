"""agents-md detection and import preview."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from self_nomad.adapters.agents_md import AgentsMdAdapter, daily_runtime_relative
from self_nomad.application import SelfNomad
from self_nomad.cli import app
from self_nomad.domain import Fidelity

runner = CliRunner()
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "agents_md"


def test_readme_only_is_not_a_candidate(tmp_path: Path) -> None:
    workspace = tmp_path / "readme"
    shutil.copytree(FIXTURES / "readme_only", workspace)
    found = AgentsMdAdapter().detect(workspace)
    assert found.candidates == []


def test_happy_import_marks_agents_adapted_and_keeps_daily(tmp_path: Path) -> None:
    workspace = tmp_path / "happy"
    shutil.copytree(FIXTURES / "happy", workspace)
    repo = SelfNomad.initialize(tmp_path / "self", name="ws", initialize_git=False)
    adapter = AgentsMdAdapter()
    found = adapter.detect(workspace)
    assert len(found.candidates) == 1
    plan = adapter.plan_import(found.candidates[0], repo.repository)
    instructions = next(item for item in plan.mappings if item.artifact == "instructions")
    assert instructions.fidelity == Fidelity.ADAPTED
    assert instructions.reason and "AGENTS.md" in instructions.reason
    assert any(item.artifact == "daily_memory" for item in plan.mappings)
    assert any(item.artifact == "knowledge" for item in plan.exclusions)
    names = {item.artifact for item in plan.exclusions}
    assert "credentials" in names


def test_env_file_is_not_materialized(tmp_path: Path) -> None:
    workspace = tmp_path / "env"
    shutil.copytree(FIXTURES / "with_env", workspace)
    repo = SelfNomad.initialize(tmp_path / "self", name="ws", initialize_git=False)
    adapter = AgentsMdAdapter()
    plan = adapter.plan_import(adapter.detect(workspace).candidates[0], repo.repository)
    assert any(
        item.fidelity == Fidelity.EXCLUDED_SENSITIVE and item.artifact == "credentials"
        for item in plan.exclusions
    )
    staging = tmp_path / "stage"
    adapter.materialize_import(plan, staging)
    payload = b"".join(path.read_bytes() for path in staging.rglob("*") if path.is_file())
    assert b"SECRET_SENTINEL" not in payload


def test_mixed_memory_directory_is_unmapped(tmp_path: Path) -> None:
    memory = tmp_path / "memory"
    memory.mkdir()
    (memory / "MEMORY.md").write_text("dump\n", encoding="utf-8")
    (memory / "2026-09-18.md").write_text("note\n", encoding="utf-8")
    assert daily_runtime_relative(tmp_path) is None


def test_cli_detect_and_import_preview(tmp_path: Path) -> None:
    workspace = FIXTURES / "happy"
    repo = tmp_path / "self"
    init = runner.invoke(
        app,
        ["--json", "init", str(repo), "--name", "ws", "--no-git"],
        catch_exceptions=False,
    )
    assert init.exit_code == 0, init.stdout
    detected = runner.invoke(
        app,
        [
            "--json",
            "--repo",
            str(repo),
            "detect",
            "--adapter",
            "agents-md",
            "--path",
            str(workspace),
        ],
        catch_exceptions=False,
    )
    assert detected.exit_code == 0, detected.stdout
    body = json.loads(detected.stdout)
    assert body["result"]["candidates"]
    preview = runner.invoke(
        app,
        [
            "--json",
            "--repo",
            str(repo),
            "import",
            "--adapter",
            "agents-md",
            "--from",
            str(workspace),
        ],
        catch_exceptions=False,
    )
    assert preview.exit_code == 0, preview.stdout
    plan = json.loads(preview.stdout)["result"]["plan"]
    assert plan["direction"] == "import"
    adapted = [
        item
        for item in plan["mappings"]
        if item["artifact"] == "instructions" and item["fidelity"] == "adapted"
    ]
    assert adapted
    assert any(item["artifact"] == "credentials" for item in plan["exclusions"])
    assert json.loads(preview.stdout)["result"]["applied"] is False
