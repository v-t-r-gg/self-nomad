"""Contract tests every RuntimeAdapter must pass, including the kit sample."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from self_nomad.adapters import (
    AgentsMdAdapter,
    ClaudeCodeAdapter,
    HermesAdapter,
    OpenClawAdapter,
    default_registry,
)
from self_nomad.adapters.example import ExampleFilesAdapter
from self_nomad.application import SelfNomad
from self_nomad.domain import Fidelity, RuntimeRef

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _repo(tmp_path: Path) -> SelfNomad:
    return SelfNomad.initialize(tmp_path / "self", name="kit", initialize_git=False)


@pytest.mark.parametrize(
    ("adapter", "fixture_relative", "forbidden"),
    [
        (HermesAdapter(), "hermes/minimal", (b"SECRET_SENTINEL", b"SESSION_SENTINEL")),
        (OpenClawAdapter(), "openclaw/minimal", (b"BOOTSTRAP",)),
        (ExampleFilesAdapter(), "example-files/minimal", (b"SECRET_SENTINEL",)),
        (AgentsMdAdapter(), "agents_md/with_env", (b"SECRET_SENTINEL",)),
        (ClaudeCodeAdapter(), "claude_code/both", (b"SECRET_SENTINEL", b"DO_NOT_MERGE")),
    ],
)
def test_adapter_contract_import_excludes_sensitive(
    tmp_path: Path,
    adapter: (
        HermesAdapter | OpenClawAdapter | ExampleFilesAdapter | AgentsMdAdapter | ClaudeCodeAdapter
    ),
    fixture_relative: str,
    forbidden: tuple[bytes, ...],
) -> None:
    runtime_root = tmp_path / "runtime"
    source = FIXTURES / fixture_relative
    if source.is_dir():
        import shutil

        shutil.copytree(source, runtime_root)
    app = _repo(tmp_path)
    detection = adapter.detect(runtime_root)
    assert detection.adapter == adapter.name
    assert len(detection.candidates) == 1
    plan = adapter.plan_import(detection.candidates[0], app.repository)
    assert plan.direction == "import"
    assert plan.mappings
    artifacts = {item.artifact for item in plan.exclusions}
    assert any(
        item.fidelity in {Fidelity.EXCLUDED_SENSITIVE, Fidelity.RUNTIME_OWNED, Fidelity.UNSUPPORTED}
        for item in plan.exclusions
    )
    assert {"knowledge", "workflows", "evaluations"} <= artifacts
    staging = tmp_path / "staging"
    adapter.materialize_import(plan, staging)
    payload = b"".join(path.read_bytes() for path in staging.rglob("*") if path.is_file())
    for token in forbidden:
        if token == b"BOOTSTRAP":
            assert not (staging / "BOOTSTRAP.md").exists()
            continue
        assert token not in payload
    result = adapter.validate(app.repository, detection.candidates[0])
    assert result.content_digest
    source_text = Path(inspect.getfile(adapter.__class__)).read_text(encoding="utf-8")
    assert "GitBackend" not in source_text


def test_example_files_not_in_default_registry() -> None:
    assert "example-files" not in default_registry().names()
    assert {"hermes", "openclaw", "agents-md", "claude-code"} <= set(default_registry().names())


def test_hermes_and_openclaw_report_unmapped_classes(tmp_path: Path) -> None:
    app = _repo(tmp_path)
    runtime = RuntimeRef(adapter="hermes", root=tmp_path / "empty", name="empty")
    (tmp_path / "empty").mkdir()
    hermes_plan = HermesAdapter().plan_restore(app.repository, runtime)
    excluded = {item.artifact for item in hermes_plan.exclusions}
    assert {"knowledge", "workflows", "evaluations", "instructions"} <= excluded
    openclaw_plan = OpenClawAdapter().plan_restore(
        app.repository, RuntimeRef(adapter="openclaw", root=tmp_path / "empty", name="empty")
    )
    openclaw_excluded = {item.artifact for item in openclaw_plan.exclusions}
    assert {"knowledge", "workflows", "evaluations"} <= openclaw_excluded
    instructions = next(
        item for item in openclaw_plan.mappings if item.artifact == "instructions"
    )
    assert instructions.fidelity == Fidelity.ADAPTED
    assert instructions.reason and "AGENTS.md" in instructions.reason
