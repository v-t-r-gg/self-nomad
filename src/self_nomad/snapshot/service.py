"""Build and verify history-free self-nomad snapshot packs."""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import yaml

from self_nomad.errors import ConflictError, PackError, ValidationFailedError
from self_nomad.filesystem import contained_path
from self_nomad.manifest import Manifest
from self_nomad.manifest.loader import load_yaml
from self_nomad.policy import Policy
from self_nomad.repository import SelfRepository
from self_nomad.snapshot.models import (
    PACK_SIDECAR,
    PackIdentity,
    PackPolicyHighlights,
    PackProfile,
    PackSummary,
)

SPECIALIST_OMIT_ALWAYS = ("user_profile", "daily_memory")
LONG_TERM_FIELD = "long_term_memory"
SHAREABLE_LONG_TERM = "memory/PUBLISH.md"
DUMP_LONG_TERM = "memory/MEMORY.md"
# Absolute ceilings for untrusted archives. Independent of repository policy
# so a crafted tar cannot expand the validator without bound.
ARCHIVE_MAX_MEMBERS = 4096
ARCHIVE_MAX_MEMBER_BYTES = 8 * 1024 * 1024
ARCHIVE_MAX_TOTAL_BYTES = 64 * 1024 * 1024


class SnapshotService:
    def __init__(self, repository: SelfRepository) -> None:
        self.repository = repository

    def pack(
        self,
        destination: Path,
        *,
        profile: PackProfile = "specialist",
        include_long_term_memory: bool = False,
    ) -> PackSummary:
        source = self.repository.validate(strict=True)
        if not source.valid:
            raise ValidationFailedError(
                "; ".join(f"{item.code}: {item.message}" for item in source.findings)
            )
        omitted = _omitted_fields(profile, include_long_term_memory=include_long_term_memory)
        original = self.repository.load_manifest()
        export = _export_manifest(
            original,
            omitted,
            source_root=self.repository.root,
            profile=profile,
            include_long_term_memory=include_long_term_memory,
        )
        staging = Path(tempfile.mkdtemp(prefix="self-nomad-pack-"))
        try:
            _stage_export(self.repository.root, staging, export)
            staged = SelfRepository(staging)
            validation = staged.validate(strict=True)
            if not validation.valid:
                raise ValidationFailedError(
                    "; ".join(f"{item.code}: {item.message}" for item in validation.findings)
                )
            summary = _build_summary(
                export,
                profile=profile,
                omitted=omitted,
                digest=validation.content_digest,
                root=staging,
            )
            (staging / PACK_SIDECAR).write_text(
                summary.model_dump_json(indent=2) + "\n",
                encoding="utf-8",
            )
            _assert_archive_budget(staging)
            _write_archive(staging, destination)
            return summary
        finally:
            shutil.rmtree(staging, ignore_errors=True)


@contextmanager
def _opened_pack(archive: Path) -> Iterator[tuple[Path, PackSummary]]:
    if not archive.is_file():
        raise PackError(f"pack not found: {archive}")
    staging = Path(tempfile.mkdtemp(prefix="self-nomad-pack-open-"))
    try:
        _extract_archive(archive, staging)
        if (staging / ".git").exists():
            raise PackError("pack must not contain Git history")
        sidecar = staging / PACK_SIDECAR
        if not sidecar.is_file():
            raise PackError(f"pack is missing {PACK_SIDECAR}")
        summary = PackSummary.model_validate_json(sidecar.read_text(encoding="utf-8"))
        _assert_profile_closure(staging, summary)
        validation = SelfRepository(staging).validate(strict=True)
        if not validation.valid:
            raise ValidationFailedError(
                "; ".join(f"{item.code}: {item.message}" for item in validation.findings)
            )
        if validation.content_digest != summary.content_digest:
            raise PackError("pack content_digest does not match the archived tree")
        yield staging, summary
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def check_pack(archive: Path, *, profile: str = "specialist") -> PackSummary:
    """Verify an archive. Personal packs pass only when ``profile="personal"``."""
    if profile not in ("specialist", "personal"):
        raise ConflictError("profile must be specialist or personal")
    with _opened_pack(archive) as (_staging, summary):
        if summary.profile != profile:
            raise PackError(
                f"pack profile is {summary.profile}; "
                f"pass profile {summary.profile!r} to accept it"
            )
        return summary


def list_pack(archive: Path) -> tuple[PackSummary, list[str]]:
    """Read the sidecar and member names without writing the tree."""
    if not archive.is_file():
        raise PackError(f"pack not found: {archive}")
    sidecar_bytes: bytes | None = None
    names: list[str] = []
    try:
        with tarfile.open(archive, "r:gz") as handle:
            for member in _checked_members(handle):
                names.append(member.name)
                if member.name == PACK_SIDECAR and member.isfile():
                    extracted = handle.extractfile(member)
                    if extracted is None:
                        raise PackError(f"pack member cannot be read: {member.name}")
                    sidecar_bytes = extracted.read(ARCHIVE_MAX_MEMBER_BYTES + 1)
                    if len(sidecar_bytes) > ARCHIVE_MAX_MEMBER_BYTES:
                        raise PackError(f"pack member exceeds size cap: {member.name}")
    except tarfile.TarError as exc:
        raise PackError(f"pack is not a readable gzip tar: {exc}") from exc
    if sidecar_bytes is None:
        raise PackError(f"pack is missing {PACK_SIDECAR}")
    return PackSummary.model_validate_json(sidecar_bytes), names


def install_pack(
    archive: Path,
    destination: Path,
    *,
    initialize_git: bool = True,
) -> tuple[SelfRepository, PackSummary]:
    destination = destination.resolve()
    if destination.exists() and (destination.is_file() or any(destination.iterdir())):
        raise ConflictError(f"destination is not empty: {destination}")
    with _opened_pack(archive) as (staging, summary):
        if destination.exists():
            destination.rmdir()
        shutil.copytree(staging, destination, symlinks=False)
    gitignore = destination / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(".self-nomad.local.yaml\n", encoding="utf-8")
    if initialize_git:
        _init_git(destination)
    return SelfRepository(destination), summary


def _init_git(path: Path) -> None:
    from self_nomad.git import GitBackend

    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    try:
        subprocess.run(
            ["git", "init", "--quiet", "--initial-branch=main", "--", str(path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
            env=environment,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise PackError(f"could not initialize git at destination: {exc}") from exc
    backend = GitBackend(path)
    backend.ensure_local_identity()
    backend.commit_all(path, "self-nomad: installed snapshot")


def _omitted_fields(profile: PackProfile, *, include_long_term_memory: bool) -> tuple[str, ...]:
    if profile == "personal":
        return ()
    omitted = list(SPECIALIST_OMIT_ALWAYS)
    if not include_long_term_memory:
        omitted.append(LONG_TERM_FIELD)
    return tuple(omitted)


def _export_manifest(
    original: Manifest,
    omitted: tuple[str, ...],
    *,
    source_root: Path,
    profile: PackProfile,
    include_long_term_memory: bool,
) -> Manifest:
    content = original.content.model_copy()
    for field in omitted:
        setattr(content, field, None)
    if profile == "specialist" and include_long_term_memory:
        shareable = source_root / SHAREABLE_LONG_TERM
        if not shareable.is_file() or shareable.is_symlink():
            raise PackError(
                "specialist --include-long-term-memory requires "
                f"{SHAREABLE_LONG_TERM}; memory/MEMORY.md is not packed"
            )
        content.long_term_memory = SHAREABLE_LONG_TERM
    return original.model_copy(update={"content": content})


def _normalized_bytes(data: bytes) -> bytes:
    """UTF-8 text is stored with LF newlines. Non-text bytes are unchanged.

    Digest stability does not depend on the host's newline convention.
    """
    if b"\0" in data:
        return data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _copy_normalized_file(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise PackError(f"refusing to pack special file: {source.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(_normalized_bytes(source.read_bytes()))


def _copy_normalized_tree(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_dir():
        raise PackError(f"refusing to pack special file: {source.name}")
    destination.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        target = destination / relative
        if path.is_symlink():
            raise PackError(f"refusing to pack special file: {relative.as_posix()}")
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if not path.is_file():
            raise PackError(f"refusing to pack special file: {relative.as_posix()}")
        _copy_normalized_file(path, target)


def _stage_export(source_root: Path, staging: Path, export: Manifest) -> None:
    for relative in export.authoritative_paths():
        source = contained_path(source_root, relative, must_exist=True)
        destination = staging / relative
        if source.is_dir():
            _copy_normalized_tree(source, destination)
        else:
            _copy_normalized_file(source, destination)
    (staging / "self-nomad.yaml").write_text(_dump_manifest(export), encoding="utf-8")


def _dump_manifest(manifest: Manifest) -> str:
    return yaml.safe_dump(
        manifest.model_dump(mode="json", exclude_none=True),
        sort_keys=False,
        allow_unicode=True,
    )


def _build_summary(
    manifest: Manifest,
    *,
    profile: PackProfile,
    omitted: tuple[str, ...],
    digest: str,
    root: Path,
) -> PackSummary:
    policy_path = contained_path(root, manifest.policy, must_exist=True)
    policy = Policy.model_validate(load_yaml(policy_path))
    return PackSummary(
        profile=profile,
        self=PackIdentity(
            id=manifest.self.id,
            name=manifest.self.name,
            description=manifest.self.description,
        ),
        skill_format=manifest.skill_format,
        skills=_skill_names(root, manifest.content.skills),
        omitted=list(omitted),
        policy=PackPolicyHighlights(
            approval_default=policy.approval.default,
            scan_for_secrets=policy.validation.scan_for_secrets,
            maximum_file_bytes=policy.limits.maximum_file_bytes,
        ),
        content_digest=digest,
        packer_version=_packer_version(),
        created_at=datetime.now(UTC),
    )


def _packer_version() -> str:
    from self_nomad import __version__

    return __version__


def _skill_names(root: Path, skills_relative: str | None) -> list[str]:
    if not skills_relative:
        return []
    skills_root = root / skills_relative
    if not skills_root.is_dir():
        return []
    names: list[str] = []
    for child in sorted(skills_root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        names.append(_skill_name(child))
    return names


def _skill_name(directory: Path) -> str:
    skill_md = directory / "SKILL.md"
    if skill_md.is_file():
        text = skill_md.read_text(encoding="utf-8")
        if text.startswith("---"):
            _, remainder = text.split("---", 1)
            if "---" in remainder:
                front, _body = remainder.split("---", 1)
                loaded = yaml.safe_load(front) or {}
                raw_name = loaded.get("name") if isinstance(loaded, dict) else None
                if isinstance(raw_name, str):
                    name = raw_name.strip()
                    if name:
                        return name
    return directory.name


def _write_archive(staging: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        with tarfile.open(temporary, "w:gz") as archive:
            sidecar = staging / PACK_SIDECAR
            archive.add(sidecar, arcname=PACK_SIDECAR)
            for path in sorted(staging.rglob("*")):
                if not path.is_file() or path.name == PACK_SIDECAR:
                    continue
                archive.add(path, arcname=path.relative_to(staging).as_posix())
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def _extract_archive(archive: Path, destination: Path) -> None:
    try:
        with tarfile.open(archive, "r:gz") as handle:
            for member in _checked_members(handle):
                target = destination / member.name
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                extracted = handle.extractfile(member)
                if extracted is None:
                    raise PackError(f"pack member cannot be read: {member.name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                remaining = member.size
                with extracted, target.open("wb") as output:
                    while remaining > 0:
                        chunk = extracted.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        output.write(chunk)
    except PackError:
        raise
    except tarfile.TarError as exc:
        raise PackError(f"pack is not a readable gzip tar: {exc}") from exc


def _checked_members(handle: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = handle.getmembers()
    if len(members) > ARCHIVE_MAX_MEMBERS:
        raise PackError(f"pack has {len(members)} members; limit is {ARCHIVE_MAX_MEMBERS}")
    seen: set[str] = set()
    total = 0
    for member in members:
        _assert_safe_member(member)
        if member.name in seen:
            raise PackError(f"pack contains a duplicate path: {member.name}")
        seen.add(member.name)
        if not member.isfile():
            continue
        size = member.size
        if size < 0 or size > ARCHIVE_MAX_MEMBER_BYTES:
            raise PackError(f"pack member exceeds size cap: {member.name} ({size} bytes)")
        total += size
        if total > ARCHIVE_MAX_TOTAL_BYTES:
            raise PackError(
                f"pack exceeds uncompressed size cap ({ARCHIVE_MAX_TOTAL_BYTES} bytes)"
            )
    return members


def _assert_archive_budget(staging: Path) -> None:
    files = [path for path in staging.rglob("*") if path.is_file()]
    if len(files) > ARCHIVE_MAX_MEMBERS:
        raise PackError(f"pack has {len(files)} members; limit is {ARCHIVE_MAX_MEMBERS}")
    total = 0
    for path in files:
        size = path.stat().st_size
        if size > ARCHIVE_MAX_MEMBER_BYTES:
            raise PackError(f"pack member exceeds size cap: {path.name} ({size} bytes)")
        total += size
        if total > ARCHIVE_MAX_TOTAL_BYTES:
            raise PackError(
                f"pack exceeds uncompressed size cap ({ARCHIVE_MAX_TOTAL_BYTES} bytes)"
            )


def _assert_profile_closure(staging: Path, summary: PackSummary) -> None:
    if summary.profile != "specialist":
        return
    for required in SPECIALIST_OMIT_ALWAYS:
        if required not in summary.omitted:
            raise PackError(f"specialist pack must omit {required}")
    manifest = SelfRepository(staging).load_manifest()
    if manifest.content.user_profile or manifest.content.daily_memory:
        raise PackError("specialist pack must omit user_profile and daily_memory")
    files = [
        path.relative_to(staging).as_posix()
        for path in staging.rglob("*")
        if path.is_file()
    ]
    for relative in files:
        if (
            relative == "identity/user.md"
            or relative == DUMP_LONG_TERM
            or relative == "memory/daily"
            or relative.startswith("memory/daily/")
        ):
            raise PackError(f"specialist pack contains forbidden path: {relative}")
    if LONG_TERM_FIELD in summary.omitted:
        if manifest.content.long_term_memory or SHAREABLE_LONG_TERM in files:
            raise PackError("specialist pack includes long-term memory that was not requested")
        return
    if manifest.content.long_term_memory != SHAREABLE_LONG_TERM:
        raise PackError(f"specialist long-term memory must be {SHAREABLE_LONG_TERM}")
    if SHAREABLE_LONG_TERM not in files:
        raise PackError(f"specialist pack is missing {SHAREABLE_LONG_TERM}")


def _assert_safe_member(member: tarfile.TarInfo) -> None:
    name = member.name.replace("\\", "/")
    if not name or name in {".", "./"}:
        raise PackError(f"pack contains an unsafe path: {member.name}")
    if name.startswith("/") or name.startswith("../") or "/../" in f"/{name}/":
        raise PackError(f"pack contains an unsafe path: {member.name}")
    parts = PurePosixPath(name).parts
    if not parts or ".." in parts or "." in parts or parts[0] == "/":
        raise PackError(f"pack contains an unsafe path: {member.name}")
    if any(part == ".git" for part in parts):
        raise PackError(f"pack contains Git history: {member.name}")
    if member.issym() or member.islnk():
        raise PackError(f"pack contains a link: {member.name}")
    if not (member.isfile() or member.isdir()):
        raise PackError(f"pack contains a special file: {member.name}")
