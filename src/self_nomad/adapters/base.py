import hashlib
import os
import shutil
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from platformdirs import user_state_path

from self_nomad.domain import (
    ApplyResult,
    DetectionResult,
    Finding,
    RuntimeRef,
    TransferPlan,
    ValidationResult,
)
from self_nomad.errors import ConflictError, RecoveryRequiredError, RestoreVerificationError
from self_nomad.filesystem import atomic_write_bytes, sha256_file
from self_nomad.manifest.schema import validate_portable_path
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


def assert_safe_tree(path: Path) -> None:
    if path.is_symlink():
        raise ConflictError(f"symlink rejected: {path}")
    if path.is_file():
        return
    for item in path.rglob("*"):
        if item.is_symlink() or (not item.is_file() and not item.is_dir()):
            raise ConflictError(f"symlink or special file rejected: {item}")


def remove_path(path: Path) -> None:
    if path.is_symlink():
        raise ConflictError(f"refusing to remove symlink: {path}")
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


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

    def apply_restore(
        self,
        plan: TransferPlan,
        *,
        backup_root: Path | None = None,
        failure_injector: Callable[[str], None] | None = None,
    ) -> ApplyResult:
        if plan.direction != "restore" or plan.conflicts:
            raise ConflictError("restore plan is not applicable")
        inject = failure_injector or (lambda _phase: None)
        runtime_root = plan.runtime.root.absolute()
        runtime_root.parent.mkdir(parents=True, exist_ok=True)
        if runtime_root.is_symlink():
            raise ConflictError("runtime root cannot be a symlink")
        original_exists = runtime_root.exists()
        original_digest: str | None = None
        if original_exists:
            if not runtime_root.is_dir():
                raise ConflictError("runtime root must be a directory")
            assert_safe_tree(runtime_root)
            original_digest = tree_digest(runtime_root)
        backup = backup_root or (
            user_state_path("self-nomad", appauthor=False)
            / "backups"
            / self.name
            / datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        )
        applicable = [
            mapping
            for mapping in plan.mappings
            if mapping.source and mapping.destination and mapping.action != "identical"
        ]
        for mapping in plan.mappings:
            if not mapping.destination:
                continue
            validate_portable_path(mapping.destination.as_posix())
            target = runtime_root / mapping.destination
            if mapping.before_sha256 is None:
                if mapping.action == "add" and target.exists():
                    raise ConflictError(f"runtime changed after plan: {mapping.destination}")
            elif not target.exists() or tree_digest(target) != mapping.before_sha256:
                raise ConflictError(f"runtime changed after plan: {mapping.destination}")

        if not applicable:
            return ApplyResult(
                adapter=self.name,
                written=[],
                hashes={
                    mapping.destination.as_posix(): tree_digest(mapping.source)
                    for mapping in plan.mappings
                    if mapping.source and mapping.destination
                },
            )

        stage = Path(
            tempfile.mkdtemp(
                prefix=f".{runtime_root.name}.self-nomad-stage-", dir=runtime_root.parent
            )
        )
        rollback = runtime_root.parent / f".{runtime_root.name}.self-nomad-rollback-{uuid4()}"
        swapped = False
        hashes: dict[str, str] = {}
        try:
            if original_exists:
                shutil.copytree(runtime_root, stage, dirs_exist_ok=True, copy_function=shutil.copy2)
            for mapping in applicable:
                assert mapping.source is not None and mapping.destination is not None
                staged_target = stage / mapping.destination
                if staged_target.exists():
                    remove_path(staged_target)
                copy_artifact(mapping.source, staged_target)
            inject("after_stage")

            for mapping in plan.mappings:
                if not mapping.source or not mapping.destination:
                    continue
                staged_target = stage / mapping.destination
                if not staged_target.exists() or tree_digest(staged_target) != tree_digest(
                    mapping.source
                ):
                    raise RestoreVerificationError(
                        f"staged restore verification failed: {mapping.destination}"
                    )
            inject("after_stage_verify")

            if original_exists and tree_digest(runtime_root) != original_digest:
                raise ConflictError("runtime changed while restore was staging")

            for mapping in applicable:
                assert mapping.destination is not None
                original = runtime_root / mapping.destination
                if original.exists():
                    copy_artifact(original, backup / mapping.destination)
            inject("after_backup")

            if original_exists:
                os.replace(runtime_root, rollback)
            inject("after_original_move")
            os.replace(stage, runtime_root)
            swapped = True
            inject("after_stage_move")

            for mapping in plan.mappings:
                if not mapping.source or not mapping.destination:
                    continue
                live = runtime_root / mapping.destination
                actual = tree_digest(live)
                if actual != tree_digest(mapping.source):
                    raise RestoreVerificationError(
                        f"live restore verification failed: {mapping.destination}"
                    )
                hashes[mapping.destination.as_posix()] = actual
            inject("after_live_verify")
        except Exception as exc:
            try:
                if swapped and runtime_root.exists():
                    remove_path(runtime_root)
                if rollback.exists():
                    os.replace(rollback, runtime_root)
                elif not original_exists and runtime_root.exists():
                    remove_path(runtime_root)
            except Exception as recovery_exc:
                raise RecoveryRequiredError(
                    f"restore failed ({exc}); automatic rollback failed ({recovery_exc}); "
                    f"recovery copy: {rollback}"
                ) from recovery_exc
            raise
        finally:
            if stage.exists():
                remove_path(stage)
        if rollback.exists():
            remove_path(rollback)
        written = [
            runtime_root / mapping.destination for mapping in applicable if mapping.destination
        ]
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
