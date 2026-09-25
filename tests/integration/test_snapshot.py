"""History-free snapshot pack and check."""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest

from self_nomad.adapters import default_registry
from self_nomad.application import SelfNomad
from self_nomad.domain import RuntimeRef
from self_nomad.errors import ConflictError, PackError, ValidationFailedError
from self_nomad.snapshot import PACK_SIDECAR
from tests.helpers import ensure_initial_commit, run_git


def _agent_with_skill(tmp_path: Path) -> SelfNomad:
    app = SelfNomad.initialize(tmp_path / "agent", name="packer")
    ensure_initial_commit(app.repository.root)
    skill = app.repository.root / "skills" / "research"
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(
        "---\nname: research\ndescription: Look things up.\n---\n\n# Research\n",
        encoding="utf-8",
    )
    (app.repository.root / "memory" / "MEMORY.md").write_text(
        "# Memory\n\n- A personal fact.\n",
        encoding="utf-8",
    )
    (app.repository.root / "identity" / "user.md").write_text(
        "# User\n\nThe operator.\n",
        encoding="utf-8",
    )
    return app


def _names(archive: Path) -> set[str]:
    with tarfile.open(archive, "r:gz") as handle:
        return set(handle.getnames())


def test_specialist_pack_omits_personal_artifacts(tmp_path: Path) -> None:
    app = _agent_with_skill(tmp_path)
    archive = tmp_path / "specialist.snpack"
    summary = app.pack(archive, profile="specialist")
    names = _names(archive)
    assert PACK_SIDECAR in names
    assert "self-nomad.yaml" in names
    assert "identity/persona.md" in names
    assert "identity/user.md" not in names
    assert "memory/MEMORY.md" not in names
    assert not any(name.startswith("memory/daily") for name in names)
    assert not any(name == ".git" or name.startswith(".git/") for name in names)
    assert "user_profile" in summary.omitted
    assert "daily_memory" in summary.omitted
    assert "long_term_memory" in summary.omitted
    assert summary.skills == ["research"]
    assert (app.repository.root / "identity" / "user.md").is_file()
    checked = SelfNomad.check_pack(archive)
    assert checked.content_digest == summary.content_digest
    assert checked.self.name == "packer"


def test_personal_pack_keeps_memory_and_user(tmp_path: Path) -> None:
    app = _agent_with_skill(tmp_path)
    archive = tmp_path / "personal.snpack"
    summary = app.pack(archive, profile="personal")
    names = _names(archive)
    assert "identity/user.md" in names
    assert "memory/MEMORY.md" in names
    assert summary.omitted == []
    SelfNomad.check_pack(archive)


def test_specialist_can_allow_long_term_memory(tmp_path: Path) -> None:
    app = _agent_with_skill(tmp_path)
    archive = tmp_path / "facts.snpack"
    summary = app.pack(archive, profile="specialist", include_long_term_memory=True)
    names = _names(archive)
    assert "memory/MEMORY.md" in names
    assert "identity/user.md" not in names
    assert "long_term_memory" not in summary.omitted
    assert "user_profile" in summary.omitted


def test_check_pack_rejects_digest_mismatch(tmp_path: Path) -> None:
    app = _agent_with_skill(tmp_path)
    archive = tmp_path / "tamper.snpack"
    app.pack(archive, profile="specialist")
    staging = tmp_path / "unpacked"
    staging.mkdir()
    with tarfile.open(archive, "r:gz") as handle:
        handle.extractall(staging)
    sidecar = json.loads((staging / PACK_SIDECAR).read_text(encoding="utf-8"))
    sidecar["content_digest"] = "0" * 64
    (staging / PACK_SIDECAR).write_text(json.dumps(sidecar), encoding="utf-8")
    bad = tmp_path / "bad.snpack"
    with tarfile.open(bad, "w:gz") as handle:
        for path in staging.rglob("*"):
            if path.is_file():
                handle.add(path, arcname=path.relative_to(staging).as_posix())
    with pytest.raises(PackError, match="content_digest"):
        SelfNomad.check_pack(bad)


def test_pack_requires_valid_repository(tmp_path: Path) -> None:
    app = _agent_with_skill(tmp_path)
    (app.repository.root / "identity" / "persona.md").unlink()
    with pytest.raises(ValidationFailedError):
        app.pack(tmp_path / "nope.snpack")


def test_install_creates_validated_repo_without_git_history(tmp_path: Path) -> None:
    app = _agent_with_skill(tmp_path)
    archive = tmp_path / "spec.snpack"
    summary = app.pack(archive, profile="specialist")
    dest = tmp_path / "installed"
    installed, loaded = SelfNomad.install_pack(archive, dest)
    assert loaded.content_digest == summary.content_digest
    result = installed.repository.validate(strict=True)
    assert result.valid is True
    assert result.content_digest == summary.content_digest
    assert not (dest / "identity" / "user.md").exists()
    assert (dest / ".git").is_dir()
    assert (dest / "self-nomad.pack.json").is_file()
    log = run_git(dest, "log", "--oneline")
    assert "installed snapshot" in log
    assert log.count("\n") == 0


def test_install_without_git(tmp_path: Path) -> None:
    app = _agent_with_skill(tmp_path)
    archive = tmp_path / "spec.snpack"
    app.pack(archive, profile="specialist")
    dest = tmp_path / "bare"
    SelfNomad.install_pack(archive, dest, initialize_git=False)
    assert not (dest / ".git").exists()
    assert SelfNomad.open(dest).repository.validate(strict=True).valid


def test_install_refuses_nonempty_destination(tmp_path: Path) -> None:
    app = _agent_with_skill(tmp_path)
    archive = tmp_path / "spec.snpack"
    app.pack(archive, profile="specialist")
    dest = tmp_path / "taken"
    dest.mkdir()
    (dest / "already.txt").write_text("nope", encoding="utf-8")
    with pytest.raises(ConflictError, match="not empty"):
        SelfNomad.install_pack(archive, dest)


def test_install_refuses_path_escape_pack(tmp_path: Path) -> None:
    evil = tmp_path / "escape.snpack"
    with tarfile.open(evil, "w:gz") as handle:
        info = tarfile.TarInfo(name="../evil.txt")
        data = b"escaped\n"
        info.size = len(data)
        handle.addfile(info, fileobj=io.BytesIO(data))
    with pytest.raises(PackError, match="unsafe path"):
        SelfNomad.install_pack(evil, tmp_path / "out")


def test_install_refuses_symlink_pack(tmp_path: Path) -> None:
    evil = tmp_path / "link.snpack"
    with tarfile.open(evil, "w:gz") as handle:
        info = tarfile.TarInfo(name="hook")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        handle.addfile(info)
    with pytest.raises(PackError, match="link"):
        SelfNomad.install_pack(evil, tmp_path / "out")


def test_install_then_restore_preview(tmp_path: Path) -> None:
    app = _agent_with_skill(tmp_path)
    archive = tmp_path / "spec.snpack"
    app.pack(archive, profile="specialist")
    installed, _summary = SelfNomad.install_pack(archive, tmp_path / "restored")
    target = tmp_path / "openclaw"
    plan = default_registry().get("openclaw").plan_restore(
        installed.repository,
        RuntimeRef(adapter="openclaw", root=target, name=target.name),
    )
    assert plan.direction == "restore"
    assert not target.exists()
