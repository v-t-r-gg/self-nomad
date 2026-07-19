import shutil
from pathlib import Path

from self_nomad.adapters import HermesAdapter, OpenClawAdapter
from self_nomad.application import SelfNomad
from self_nomad.domain import Fidelity, RuntimeRef

FIXTURES = Path(__file__).parents[1] / "fixtures"


def repository(tmp_path: Path) -> SelfNomad:
    return SelfNomad.initialize(tmp_path / "self", name="portable", initialize_git=False)


def test_hermes_detect_import_excludes_secrets_and_state(tmp_path: Path) -> None:
    runtime_root = tmp_path / "hermes"
    shutil.copytree(FIXTURES / "hermes/minimal", runtime_root)
    app = repository(tmp_path)
    adapter = HermesAdapter()
    detection = adapter.detect(runtime_root)
    assert len(detection.candidates) == 1

    plan = adapter.plan_import(detection.candidates[0], app.repository)
    assert {item.artifact for item in plan.mappings} == {
        "persona",
        "long_term_memory",
        "user_profile",
        "skills",
    }
    assert {item.fidelity for item in plan.exclusions} == {
        Fidelity.EXCLUDED_SENSITIVE,
        Fidelity.RUNTIME_OWNED,
    }
    staging = tmp_path / "staging"
    adapter.materialize_import(plan, staging)
    all_content = b"".join(path.read_bytes() for path in staging.rglob("*") if path.is_file())
    assert b"SECRET_SENTINEL" not in all_content
    assert b"SESSION_SENTINEL" not in all_content


def test_hermes_restore_backs_up_and_verifies(tmp_path: Path) -> None:
    app = repository(tmp_path)
    (app.repository.root / "identity/persona.md").write_text("new persona", encoding="utf-8")
    runtime_root = tmp_path / "target"
    (runtime_root / "memories").mkdir(parents=True)
    (runtime_root / "SOUL.md").write_text("old persona", encoding="utf-8")
    runtime = RuntimeRef(adapter="hermes", root=runtime_root, name="target")
    adapter = HermesAdapter()
    plan = adapter.plan_restore(app.repository, runtime)
    result = adapter.apply_restore(plan, backup_root=tmp_path / "backup")
    assert (runtime_root / "SOUL.md").read_text() == "new persona"
    assert (tmp_path / "backup/SOUL.md").read_text() == "old persona"
    assert result.hashes["SOUL.md"]


def test_hermes_runtime_memory_limits_are_enforced(tmp_path: Path) -> None:
    app = repository(tmp_path)
    (app.repository.root / "memory/MEMORY.md").write_text("123456", encoding="utf-8")
    runtime_root = tmp_path / "hermes"
    runtime_root.mkdir()
    (runtime_root / "config.yaml").write_text(
        "memory:\n  memory_char_limit: 5\n  user_char_limit: 100\n", encoding="utf-8"
    )
    runtime = RuntimeRef(adapter="hermes", root=runtime_root, name="hermes")
    result = HermesAdapter().validate(app.repository, runtime)
    assert not result.valid
    assert any(item.code == "SN3101" for item in result.findings)


def test_openclaw_import_and_bootstrap_exclusion(tmp_path: Path) -> None:
    runtime_root = tmp_path / "workspace"
    shutil.copytree(FIXTURES / "openclaw/minimal", runtime_root)
    app = repository(tmp_path)
    adapter = OpenClawAdapter()
    runtime = adapter.detect(runtime_root).candidates[0]
    plan = adapter.plan_import(runtime, app.repository)
    assert any(
        item.artifact == "instructions" and item.fidelity == Fidelity.ADAPTED
        for item in plan.mappings
    )
    assert [item.artifact for item in plan.exclusions] == ["bootstrap"]
    staging = tmp_path / "staging"
    adapter.materialize_import(plan, staging)
    assert not (staging / "BOOTSTRAP.md").exists()
    assert (staging / "identity/instructions.md").read_text().startswith("# Instructions")


def test_one_canonical_repository_restores_to_both_runtimes(tmp_path: Path) -> None:
    app = repository(tmp_path)
    (app.repository.root / "identity/persona.md").write_text("portable persona", encoding="utf-8")
    hermes_root = tmp_path / "hermes-target"
    openclaw_root = tmp_path / "openclaw-target"
    hermes = HermesAdapter()
    openclaw = OpenClawAdapter()
    hermes_ref = RuntimeRef(adapter="hermes", root=hermes_root, name="hermes")
    openclaw_ref = RuntimeRef(adapter="openclaw", root=openclaw_root, name="openclaw")
    hermes.apply_restore(
        hermes.plan_restore(app.repository, hermes_ref), backup_root=tmp_path / "hb"
    )
    openclaw.apply_restore(
        openclaw.plan_restore(app.repository, openclaw_ref), backup_root=tmp_path / "ob"
    )
    assert (hermes_root / "SOUL.md").read_text() == "portable persona"
    assert (openclaw_root / "SOUL.md").read_text() == "portable persona"
    assert (openclaw_root / "AGENTS.md").is_file()
