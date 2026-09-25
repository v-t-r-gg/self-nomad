"""Unit tests for adapter authoring helpers."""

from __future__ import annotations

from pathlib import Path

from self_nomad.adapters.example import ExampleFilesAdapter
from self_nomad.adapters.kit import has_portable_content, map_pair, unmapped_exclusions
from self_nomad.application import SelfNomad
from self_nomad.domain import Fidelity, RuntimeRef


def test_has_portable_content_ignores_gitkeep(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    assert has_portable_content(empty) is False
    (empty / ".gitkeep").write_text("", encoding="utf-8")
    assert has_portable_content(empty) is False
    (empty / "note.md").write_text("x", encoding="utf-8")
    assert has_portable_content(empty) is True
    assert has_portable_content(empty / "note.md") is True
    assert has_portable_content(tmp_path / "missing") is False


def test_map_pair_and_unmapped_exclusions(tmp_path: Path) -> None:
    app = SelfNomad.initialize(tmp_path / "self", name="kit", initialize_git=False)
    pair = map_pair(
        artifact="persona",
        source=tmp_path / "PERSONA.md",
        destination=Path("identity/persona.md"),
        fidelity=Fidelity.EXACT,
        action="copy",
        before_sha256=None,
    )
    assert pair.artifact == "persona"
    assert pair.action == "copy"
    exclusions = unmapped_exclusions(
        app.repository,
        (("knowledge", None, Fidelity.UNSUPPORTED, "no mapping"),),
    )
    assert exclusions[0].artifact == "knowledge"
    assert exclusions[0].action == "exclude"
    assert exclusions[0].fidelity == Fidelity.UNSUPPORTED


def test_example_files_plan_restore_uses_kit_helpers(tmp_path: Path) -> None:
    app = SelfNomad.initialize(tmp_path / "self", name="kit", initialize_git=False)
    runtime = RuntimeRef(adapter="example-files", root=tmp_path / "runtime", name="runtime")
    runtime.root.mkdir()
    plan = ExampleFilesAdapter().plan_restore(app.repository, runtime)
    assert plan.direction == "restore"
    assert plan.mappings
    assert {item.artifact for item in plan.mappings} == {"persona"}
    assert {"knowledge", "workflows", "evaluations"} <= {item.artifact for item in plan.exclusions}
