"""Thin wrappers do not merge extra instruction files into AGENTS.md."""

from __future__ import annotations

import shutil
from pathlib import Path

from self_nomad.adapters.workspace_wrappers import CopilotAdapter, CursorAdapter
from self_nomad.application import SelfNomad
from self_nomad.domain import Fidelity

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _import(tmp_path: Path, adapter, relative: str):
    workspace = tmp_path / "ws"
    shutil.copytree(FIXTURES / relative, workspace)
    repo = SelfNomad.initialize(tmp_path / "self", name="wrap", initialize_git=False)
    found = adapter.detect(workspace)
    assert len(found.candidates) == 1
    return adapter.plan_import(found.candidates[0], repo.repository)


def test_cursor_rules_are_lossy_and_not_instructions(tmp_path: Path) -> None:
    plan = _import(tmp_path, CursorAdapter(), "cursor/workspace")
    rules = [item for item in plan.exclusions if item.artifact == "cursor_rule"]
    assert rules and all(item.fidelity == Fidelity.LOSSY for item in rules)
    instructions = [item for item in plan.mappings if item.artifact == "instructions"]
    assert len(instructions) == 1
    assert instructions[0].source is not None
    assert instructions[0].source.name == "AGENTS.md"


def test_copilot_file_is_unmerged_when_agents_md_exists(tmp_path: Path) -> None:
    plan = _import(tmp_path, CopilotAdapter(), "copilot/both")
    instructions = next(item for item in plan.mappings if item.artifact == "instructions")
    assert instructions.source is not None
    assert instructions.source.name == "AGENTS.md"
    noted = [item for item in plan.exclusions if item.artifact == "copilot_instructions"]
    assert noted and noted[0].reason and "not merged" in noted[0].reason


def test_copilot_file_is_fallback_without_agents_md(tmp_path: Path) -> None:
    plan = _import(tmp_path, CopilotAdapter(), "copilot/only")
    instructions = next(item for item in plan.mappings if item.artifact == "instructions")
    assert instructions.source is not None
    assert instructions.source.name == "copilot-instructions.md"
    assert instructions.fidelity == Fidelity.ADAPTED
