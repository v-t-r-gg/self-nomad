"""Claude Code precedence: CLAUDE.md wins, AGENTS.md is not merged."""

from __future__ import annotations

import shutil
from pathlib import Path

from self_nomad.adapters.claude_code import ClaudeCodeAdapter
from self_nomad.application import SelfNomad
from self_nomad.domain import Fidelity

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "claude_code"


def _plan(tmp_path: Path, name: str):
    workspace = tmp_path / name
    shutil.copytree(FIXTURES / name, workspace)
    repo = SelfNomad.initialize(tmp_path / "self", name="claude", initialize_git=False)
    adapter = ClaudeCodeAdapter()
    found = adapter.detect(workspace)
    assert len(found.candidates) == 1
    return adapter.plan_import(found.candidates[0], repo.repository)


def test_claude_md_wins_and_agents_is_not_merged(tmp_path: Path) -> None:
    plan = _plan(tmp_path, "both")
    instructions = [item for item in plan.mappings if item.artifact == "instructions"]
    assert len(instructions) == 1
    assert instructions[0].fidelity == Fidelity.ADAPTED
    assert instructions[0].source is not None
    assert instructions[0].source.name == "CLAUDE.md"
    noted = [item for item in plan.exclusions if item.artifact == "agents_md"]
    assert noted and noted[0].reason and "not merged" in noted[0].reason


def test_agents_md_is_fallback_when_claude_md_is_absent(tmp_path: Path) -> None:
    plan = _plan(tmp_path, "agents_only")
    instructions = next(item for item in plan.mappings if item.artifact == "instructions")
    assert instructions.source is not None
    assert instructions.source.name == "AGENTS.md"
    assert instructions.fidelity == Fidelity.ADAPTED
    assert not any(item.artifact == "agents_md" for item in plan.exclusions)


def test_dot_claude_alone_has_no_instruction_mapping(tmp_path: Path) -> None:
    plan = _plan(tmp_path, "dot_only")
    assert not any(item.artifact == "instructions" for item in plan.mappings)
    noted = [item for item in plan.exclusions if item.artifact == "instructions"]
    assert noted and noted[0].reason and "no CLAUDE.md" in noted[0].reason
