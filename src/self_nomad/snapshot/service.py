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
        export = _export_manifest(original, omitted)
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


def check_pack(archive: Path) -> PackSummary:
    with _opened_pack(archive) as (_staging, summary):
        return summary


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


def _export_manifest(original: Manifest, omitted: tuple[str, ...]) -> Manifest:
    content = original.content.model_copy()
    for field in omitted:
        setattr(content, field, None)
    return original.model_copy(update={"content": content})


def _stage_export(source_root: Path, staging: Path, export: Manifest) -> None:
    for relative in export.authoritative_paths():
        source = contained_path(source_root, relative, must_exist=True)
        destination = staging / relative
        if source.is_dir():
            shutil.copytree(source, destination, symlinks=False)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
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
        created_at=datetime.now(UTC),
    )


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
            for member in handle.getmembers():
                _assert_safe_member(member)
                target = destination / member.name
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                extracted = handle.extractfile(member)
                if extracted is None:
                    raise PackError(f"pack member cannot be read: {member.name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with extracted, target.open("wb") as output:
                    shutil.copyfileobj(extracted, output)
    except tarfile.TarError as exc:
        raise PackError(f"pack is not a readable gzip tar: {exc}") from exc


def _assert_safe_member(member: tarfile.TarInfo) -> None:
    name = member.name.replace("\\", "/")
    if name.startswith("/") or name.startswith("../") or "/../" in f"/{name}/":
        raise PackError(f"pack contains an unsafe path: {member.name}")
    parts = PurePosixPath(name).parts
    if ".." in parts or (parts and parts[0] == "/"):
        raise PackError(f"pack contains an unsafe path: {member.name}")
    if member.issym() or member.islnk():
        raise PackError(f"pack contains a link: {member.name}")
    if not (member.isfile() or member.isdir()):
        raise PackError(f"pack contains a special file: {member.name}")
