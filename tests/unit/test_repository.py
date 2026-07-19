from pathlib import Path

from self_nomad.application import SelfNomad
from self_nomad.repository import SelfRepository


def test_initialize_creates_strictly_valid_repository(tmp_path: Path) -> None:
    app = SelfNomad.initialize(tmp_path / "agent", name="example", initialize_git=False)
    result = app.repository.validate(strict=True)
    assert result.valid, result.findings
    assert (app.repository.root / ".gitignore").read_text() == ".self-nomad.local.yaml\n"


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

