"""Untrusted pack/install fixtures. Calls the shipped check and install entry points."""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest

from self_nomad.application import SelfNomad
from self_nomad.errors import ConflictError, PackError, ValidationFailedError
from self_nomad.snapshot import PACK_SIDECAR
from self_nomad.snapshot.service import (
    ARCHIVE_MAX_MEMBER_BYTES,
    ARCHIVE_MAX_MEMBERS,
    ARCHIVE_MAX_TOTAL_BYTES,
)
from tests.helpers import ensure_initial_commit


def _agent(tmp_path: Path) -> SelfNomad:
    app = SelfNomad.initialize(tmp_path / "agent", name="packer")
    ensure_initial_commit(app.repository.root)
    skill = app.repository.root / "skills" / "research"
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(
        "---\nname: research\ndescription: Look things up.\n---\n\n# Research\n",
        encoding="utf-8",
    )
    (app.repository.root / "identity" / "user.md").write_text(
        "# User\n\nThe operator.\n",
        encoding="utf-8",
    )
    (app.repository.root / "memory" / "daily" / "2026-01-01.md").write_text(
        "today\n",
        encoding="utf-8",
    )
    (app.repository.root / "memory" / "MEMORY.md").write_text(
        "# Memory\n\n- personal\n",
        encoding="utf-8",
    )
    return app


def _pack(tmp_path: Path, *, profile: str = "specialist") -> Path:
    archive = tmp_path / f"{profile}.snpack"
    _agent(tmp_path).pack(archive, profile=profile)
    return archive


def _extract(archive: Path, dest: Path) -> None:
    with tarfile.open(archive, "r:gz") as handle:
        if "filter" in tarfile.TarFile.extractall.__code__.co_varnames:
            handle.extractall(dest, filter="data")
        else:
            handle.extractall(dest)


def _tar(path: Path, members: list[tuple[str, bytes | None, str | None]]) -> None:
    """Write a gzip tar. ``link`` set means a symlink; bytes None means a directory."""
    with tarfile.open(path, "w:gz") as handle:
        for name, payload, link in members:
            info = tarfile.TarInfo(name)
            if link is not None:
                info.type = tarfile.SYMTYPE
                info.linkname = link
                handle.addfile(info)
                continue
            if payload is None:
                info.type = tarfile.DIRTYPE
                handle.addfile(info)
                continue
            info.size = len(payload)
            handle.addfile(info, io.BytesIO(payload))


def test_check_and_install_reject_path_escape(tmp_path: Path) -> None:
    archive = tmp_path / "escape.snpack"
    _tar(archive, [("../evil.txt", b"escaped\n", None), ("foo/../../etc/passwd", b"nope\n", None)])
    with pytest.raises(PackError, match="unsafe path"):
        SelfNomad.check_pack(archive)
    with pytest.raises(PackError, match="unsafe path"):
        SelfNomad.install_pack(archive, tmp_path / "out")


def test_check_and_install_reject_planted_git(tmp_path: Path) -> None:
    archive = tmp_path / "git.snpack"
    _tar(archive, [(".git/config", b"[core]\n", None), (PACK_SIDECAR, b"{}\n", None)])
    with pytest.raises(PackError, match="Git history"):
        SelfNomad.check_pack(archive)
    with pytest.raises(PackError, match="Git history"):
        SelfNomad.install_pack(archive, tmp_path / "out")


def test_check_and_install_reject_symlink(tmp_path: Path) -> None:
    archive = tmp_path / "link.snpack"
    _tar(archive, [("hook", None, "/etc/passwd")])
    with pytest.raises(PackError, match="link"):
        SelfNomad.check_pack(archive)
    with pytest.raises(PackError, match="link"):
        SelfNomad.install_pack(archive, tmp_path / "out")


def test_oversize_member_is_rejected_before_extract(tmp_path: Path) -> None:
    archive = tmp_path / "big.snpack"
    payload = b"x" * (ARCHIVE_MAX_MEMBER_BYTES + 1)
    _tar(archive, [("big.bin", payload, None)])
    with pytest.raises(PackError, match="size cap"):
        SelfNomad.check_pack(archive)


def test_member_count_cap(tmp_path: Path) -> None:
    archive = tmp_path / "many.snpack"
    with tarfile.open(archive, "w:gz") as handle:
        for index in range(ARCHIVE_MAX_MEMBERS + 1):
            info = tarfile.TarInfo(f"n/{index}.txt")
            info.size = 0
            handle.addfile(info, io.BytesIO(b""))
    with pytest.raises(PackError, match="members"):
        SelfNomad.check_pack(archive)


def test_uncompressed_total_cap(tmp_path: Path) -> None:
    archive = tmp_path / "total.snpack"
    chunk = b"y" * ARCHIVE_MAX_MEMBER_BYTES
    count = (ARCHIVE_MAX_TOTAL_BYTES // ARCHIVE_MAX_MEMBER_BYTES) + 1
    with tarfile.open(archive, "w:gz") as handle:
        for index in range(count):
            info = tarfile.TarInfo(f"part-{index}.bin")
            info.size = len(chunk)
            handle.addfile(info, io.BytesIO(chunk))
    with pytest.raises(PackError, match="uncompressed size cap"):
        SelfNomad.check_pack(archive)


def test_policy_oversize_file_fails_check(tmp_path: Path) -> None:
    app = _agent(tmp_path)
    policy = app.repository.root / "policy" / "policy.yaml"
    text = policy.read_text(encoding="utf-8")
    policy.write_text(
        text.replace("maximum_file_bytes: 1048576", "maximum_file_bytes: 32"),
        encoding="utf-8",
    )
    (app.repository.root / "identity" / "persona.md").write_text("x" * 64, encoding="utf-8")
    with pytest.raises(ValidationFailedError, match="maximum_file_bytes"):
        app.pack(tmp_path / "over.snpack")


def test_secret_in_memory_fails_personal_pack(tmp_path: Path) -> None:
    app = _agent(tmp_path)
    (app.repository.root / "memory" / "MEMORY.md").write_text(
        "# Memory\n\nAKIAIOSFODNN7EXAMPLE\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationFailedError, match="secret"):
        app.pack(tmp_path / "secret.snpack", profile="personal")


def test_specialist_archive_with_user_and_daily_fails_check(tmp_path: Path) -> None:
    archive = _pack(tmp_path)
    staging = tmp_path / "unpacked"
    staging.mkdir()
    _extract(archive, staging)
    (staging / "identity").mkdir(exist_ok=True)
    (staging / "identity" / "user.md").write_text("# User\n", encoding="utf-8")
    daily = staging / "memory" / "daily"
    daily.mkdir(parents=True)
    (daily / "note.md").write_text("today\n", encoding="utf-8")
    leaked = tmp_path / "leaked.snpack"
    with tarfile.open(leaked, "w:gz") as handle:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                handle.add(path, arcname=path.relative_to(staging).as_posix())
    with pytest.raises(PackError, match="forbidden path"):
        SelfNomad.check_pack(leaked)
    with pytest.raises(PackError, match="forbidden path"):
        SelfNomad.install_pack(leaked, tmp_path / "installed")


def test_digest_mismatch_after_bit_flip(tmp_path: Path) -> None:
    archive = _pack(tmp_path)
    staging = tmp_path / "unpacked"
    staging.mkdir()
    _extract(archive, staging)
    persona = staging / "identity" / "persona.md"
    original = persona.read_bytes()
    persona.write_bytes(original[:-1] + (b"Y" if original[-1:] != b"Y" else b"Z"))
    flipped = tmp_path / "flipped.snpack"
    with tarfile.open(flipped, "w:gz") as handle:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                handle.add(path, arcname=path.relative_to(staging).as_posix())
    with pytest.raises(PackError, match="content_digest"):
        SelfNomad.check_pack(flipped)


def test_personal_profile_rejected_unless_requested(tmp_path: Path) -> None:
    archive = _pack(tmp_path, profile="personal")
    with pytest.raises(PackError, match="profile"):
        SelfNomad.check_pack(archive)
    summary = SelfNomad.check_pack(archive, profile="personal")
    assert summary.profile == "personal"
    assert "identity/user.md" in _names(archive)


def test_install_refuses_nonempty_destination(tmp_path: Path) -> None:
    archive = _pack(tmp_path)
    dest = tmp_path / "taken"
    dest.mkdir()
    (dest / "already.txt").write_text("nope", encoding="utf-8")
    with pytest.raises(ConflictError, match="not empty"):
        SelfNomad.install_pack(archive, dest)


def test_same_tree_same_digest_and_lf_normalization(tmp_path: Path) -> None:
    app = _agent(tmp_path)
    persona = app.repository.root / "identity" / "persona.md"
    persona.write_bytes(b"# Persona\r\n\r\nSame body.\r\n")
    first = tmp_path / "a.snpack"
    second = tmp_path / "b.snpack"
    left = app.pack(first)
    persona.write_bytes(b"# Persona\n\nSame body.\n")
    right = app.pack(second)
    assert left.content_digest == right.content_digest
    staging = tmp_path / "norm"
    staging.mkdir()
    _extract(second, staging)
    stored = (staging / "identity" / "persona.md").read_bytes()
    assert b"\r" not in stored
    assert stored == b"# Persona\n\nSame body.\n"


def test_check_rejects_forged_sidecar_identity_and_skills(tmp_path: Path) -> None:
    archive = _pack(tmp_path)
    honest = SelfNomad.check_pack(archive)
    staging = tmp_path / "unpacked"
    staging.mkdir()
    _extract(archive, staging)
    sidecar_path = staging / PACK_SIDECAR
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar["skills"] = ["not-the-real-skill"]
    sidecar["self"]["name"] = "forged-name"
    sidecar["self"]["id"] = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeee1"
    assert sidecar["content_digest"] == honest.content_digest
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    forged = tmp_path / "forged.snpack"
    with tarfile.open(forged, "w:gz") as handle:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                handle.add(path, arcname=path.relative_to(staging).as_posix())
    with pytest.raises(PackError, match="does not match"):
        SelfNomad.check_pack(forged)
    with pytest.raises(PackError, match="does not match"):
        SelfNomad.install_pack(forged, tmp_path / "out")
    assert SelfNomad.check_pack(archive).content_digest == honest.content_digest
    assert SelfNomad.check_pack(archive).skills == ["research"]
    assert SelfNomad.check_pack(archive).self.name == "packer"


def _names(archive: Path) -> set[str]:
    with tarfile.open(archive, "r:gz") as handle:
        return set(handle.getnames())
