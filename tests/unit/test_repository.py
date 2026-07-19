import subprocess
from pathlib import Path

import pytest
import yaml

from self_nomad.application import SelfNomad
from self_nomad.repository import SelfRepository


def test_initialize_creates_strictly_valid_repository(tmp_path: Path) -> None:
    app = SelfNomad.initialize(tmp_path / "agent", name="example", initialize_git=False)
    result = app.repository.validate(strict=True)
    assert result.valid, result.findings
    assert (app.repository.root / ".gitignore").read_text() == ".self-nomad.local.yaml\n"


def test_git_initialization_uses_main_on_every_platform(tmp_path: Path) -> None:
    app = SelfNomad.initialize(tmp_path / "agent", name="example")
    branch = subprocess.run(
        ["git", "symbolic-ref", "--short", "HEAD"],
        cwd=app.repository.root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert branch == "main"


def test_discovery_walks_up_from_child(tmp_path: Path) -> None:
    app = SelfNomad.initialize(tmp_path / "agent", name="example", initialize_git=False)
    assert SelfRepository.discover(app.repository.root / "memory").root == app.repository.root


def test_symlinked_artifact_outside_repository_is_blocked(tmp_path: Path) -> None:
    app = SelfNomad.initialize(tmp_path / "agent", name="example", initialize_git=False)
    memory = app.repository.root / "memory/MEMORY.md"
    memory.unlink()
    outside = tmp_path / "outside.md"
    outside.write_text("private")
    memory.symlink_to(outside)
    result = app.repository.validate(strict=True)
    assert not result.valid
    assert any(finding.code == "SN1101" for finding in result.findings)


def test_nonempty_destination_is_not_overwritten(tmp_path: Path) -> None:
    target = tmp_path / "agent"
    target.mkdir()
    (target / "owned.txt").write_text("keep")
    try:
        SelfNomad.initialize(target, name="example", initialize_git=False)
    except Exception:
        pass
    else:
        raise AssertionError("initialization should have failed")
    assert (target / "owned.txt").read_text() == "keep"


def test_directory_content_changes_validation_digest(tmp_path: Path) -> None:
    app = SelfNomad.initialize(tmp_path / "agent", name="example", initialize_git=False)
    skill = app.repository.root / "skills/example"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# First\n", encoding="utf-8")
    before = app.repository.validate(strict=True).content_digest
    (skill / "SKILL.md").write_text("# Second\n", encoding="utf-8")
    after = app.repository.validate(strict=True).content_digest
    assert before != after


def test_sensitive_file_inside_artifact_tree_is_blocked(tmp_path: Path) -> None:
    app = SelfNomad.initialize(tmp_path / "agent", name="example", initialize_git=False)
    (app.repository.root / "skills/.env").write_text("TOKEN=sentinel", encoding="utf-8")
    result = app.repository.validate(strict=True)
    assert not result.valid
    assert any(finding.code == "SN1301" for finding in result.findings)


def test_high_confidence_secret_content_is_blocked(tmp_path: Path) -> None:
    app = SelfNomad.initialize(tmp_path / "agent", name="example", initialize_git=False)
    (app.repository.root / "memory/MEMORY.md").write_text(
        "github_pat_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456", encoding="utf-8"
    )
    result = app.repository.validate(strict=True)
    assert not result.valid
    assert any(finding.code == "SN1302" for finding in result.findings)


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("approval", "default", "allowed"),
        ("validation", "strict_schema", False),
        ("validation", "reject_symlinks", False),
        ("validation", "scan_for_secrets", False),
        ("validation", "execute_repository_tests", True),
    ],
)
def test_unsupported_policy_relaxations_are_rejected(
    tmp_path: Path, section: str, key: str, value: object
) -> None:
    app = SelfNomad.initialize(tmp_path / "agent", name="example", initialize_git=False)
    policy_path = app.repository.root / "policy/policy.yaml"
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    policy[section][key] = value
    policy_path.write_text(yaml.safe_dump(policy), encoding="utf-8")
    result = app.repository.validate(strict=True)
    assert not result.valid
    assert any(finding.code == "SN1002" for finding in result.findings)
