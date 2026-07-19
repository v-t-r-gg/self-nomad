import hashlib
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path

from platformdirs import user_state_path

from self_nomad.domain import (
    ApplyResult,
    DetectionResult,
    Finding,
    RuntimeRef,
    TransferPlan,
    ValidationResult,
)
from self_nomad.errors import ConflictError, RestoreVerificationError
from self_nomad.filesystem import atomic_write_bytes, sha256_file
from self_nomad.repository import SelfRepository


def tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        return sha256_file(path)
    for item in sorted(path.rglob("*")):
        if item.is_symlink() or (not item.is_file() and not item.is_dir()):
            raise ConflictError(f"unsafe file in artifact tree: {item}")
        if item.is_file():
            digest.update(item.relative_to(path).as_posix().encode())
            digest.update(sha256_file(item).encode())
    return digest.hexdigest()


def copy_artifact(source: Path, destination: Path) -> list[Path]:
    if source.is_symlink() or not (source.is_file() or source.is_dir()):
        raise ConflictError(f"unsafe artifact source: {source}")
    written: list[Path] = []
    items = [source] if source.is_file() else [item for item in source.rglob("*") if item.is_file()]
    for item in items:
        if item.is_symlink():
            raise ConflictError(f"symlink rejected: {item}")
        target = destination if source.is_file() else destination / item.relative_to(source)
        atomic_write_bytes(target, item.read_bytes(), mode=item.stat().st_mode & 0o777)
        written.append(target)
    return written


class RuntimeAdapter(ABC):
    name: str
    version = "1"

    @abstractmethod
    def detect(self, hint: Path | None = None) -> DetectionResult: ...

    @abstractmethod
    def plan_import(self, runtime: RuntimeRef, repository: SelfRepository) -> TransferPlan: ...

    @abstractmethod
    def plan_restore(self, repository: SelfRepository, runtime: RuntimeRef) -> TransferPlan: ...

    @abstractmethod
    def validate(
        self, repository: SelfRepository, runtime: RuntimeRef | None = None
    ) -> ValidationResult: ...

    def materialize_import(self, plan: TransferPlan, destination: Path) -> list[Path]:
        if plan.direction != "import":
            raise ConflictError("expected an import plan")
        written: list[Path] = []
        for mapping in plan.mappings:
            if mapping.action == "identical" or not mapping.source or not mapping.destination:
                continue
            written.extend(copy_artifact(mapping.source, destination / mapping.destination))
        return written

    def apply_restore(self, plan: TransferPlan, *, backup_root: Path | None = None) -> ApplyResult:
        if plan.direction != "restore" or plan.conflicts:
            raise ConflictError("restore plan is not applicable")
        runtime_root = plan.runtime.root
        runtime_root.mkdir(parents=True, exist_ok=True)
        runtime_root = runtime_root.resolve(strict=True)
        backup = backup_root or (
            user_state_path("self-nomad", appauthor=False)
            / "backups"
            / self.name
            / datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        )
        written: list[Path] = []
        hashes: dict[str, str] = {}
        for mapping in plan.mappings:
            if mapping.action == "identical" or not mapping.source or not mapping.destination:
                continue
            target = runtime_root / mapping.destination
            resolved_parent = target.parent.resolve(strict=False)
            if runtime_root != resolved_parent and runtime_root not in resolved_parent.parents:
                raise ConflictError(f"restore target escapes runtime: {mapping.destination}")
            if target.is_symlink():
                raise ConflictError(f"restore target is a symlink: {mapping.destination}")
            if target.exists():
                if mapping.before_sha256 and tree_digest(target) != mapping.before_sha256:
                    raise ConflictError(f"runtime changed after plan: {mapping.destination}")
                copy_artifact(target, backup / mapping.destination)
            written.extend(copy_artifact(mapping.source, target))
            actual = tree_digest(target)
            expected = tree_digest(mapping.source)
            if actual != expected:
                raise RestoreVerificationError(
                    f"restore verification failed: {mapping.destination}"
                )
            hashes[mapping.destination.as_posix()] = actual
        return ApplyResult(
            adapter=self.name,
            written=written,
            backup_root=backup if backup.exists() else None,
            hashes=hashes,
        )

    @staticmethod
    def mapping_action(source: Path, target: Path) -> tuple[str, str | None]:
        if not target.exists():
            return "add", None
        before = tree_digest(target)
        return ("identical" if tree_digest(source) == before else "replace", before)

    @staticmethod
    def skill_findings(root: Path) -> list[Finding]:
        findings: list[Finding] = []
        if not root.exists():
            return findings
        for skill in sorted(item for item in root.iterdir() if item.is_dir()):
            if not (skill / "SKILL.md").is_file():
                findings.append(
                    Finding(
                        severity="error",
                        code="SN3001",
                        message="skill directory is missing SKILL.md",
                        path=str(skill),
                    )
                )
        return findings
