import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from self_nomad.errors import ConflictError
from self_nomad.filesystem import atomic_write_text, sha256_file
from self_nomad.repository import SelfRepository
from self_nomad.repository.layout import ARTIFACT_TEMPLATES, POLICY_TEMPLATE, manifest_template

if TYPE_CHECKING:
    from self_nomad.domain import ProposalRecord, TransferPlan
    from self_nomad.intake import IntakeService
    from self_nomad.proposals import ProposalService
    from self_nomad.snapshot import PackSummary, SnapshotService


class SelfNomad:
    def __init__(self, repository: SelfRepository) -> None:
        self.repository = repository

    @classmethod
    def open(cls, path: Path) -> "SelfNomad":
        return cls(SelfRepository.discover(path))

    def proposals(self, *, state_root: Path | None = None) -> "ProposalService":
        from self_nomad.proposals import ProposalService

        return ProposalService(self.repository, state_root=state_root)

    def intake(self, *, state_root: Path | None = None) -> "IntakeService":
        from self_nomad.intake import IntakeService

        return IntakeService(self.repository, state_root=state_root)

    def snapshots(self) -> "SnapshotService":
        from self_nomad.snapshot import SnapshotService

        return SnapshotService(self.repository)

    def pack(
        self,
        destination: Path,
        *,
        profile: str = "specialist",
        include_long_term_memory: bool = False,
    ) -> "PackSummary":
        if profile == "specialist":
            return self.snapshots().pack(
                destination,
                profile="specialist",
                include_long_term_memory=include_long_term_memory,
            )
        if profile == "personal":
            return self.snapshots().pack(
                destination,
                profile="personal",
                include_long_term_memory=include_long_term_memory,
            )
        raise ConflictError("profile must be specialist or personal")

    @staticmethod
    def check_pack(archive: Path, *, profile: str = "specialist") -> "PackSummary":
        from self_nomad.snapshot.service import check_pack

        return check_pack(archive, profile=profile)

    @staticmethod
    def list_pack(archive: Path) -> tuple["PackSummary", list[str]]:
        from self_nomad.snapshot.service import list_pack

        return list_pack(archive)

    @classmethod
    def install_pack(
        cls,
        archive: Path,
        destination: Path,
        *,
        initialize_git: bool = True,
    ) -> tuple["SelfNomad", "PackSummary"]:
        from self_nomad.snapshot.service import install_pack

        repository, summary = install_pack(
            archive, destination, initialize_git=initialize_git
        )
        return cls(repository), summary

    def create_import_proposal(
        self,
        plan: "TransferPlan",
        *,
        reason: str,
        state_root: Path | None = None,
    ) -> "ProposalRecord":
        from self_nomad.adapters import default_registry
        from self_nomad.domain import FileOperation

        service = self.proposals(state_root=state_root)
        service.store.ensure_writable()
        staging = Path(tempfile.mkdtemp(prefix="import-", dir=service.store.root))
        default_registry().get(plan.adapter).materialize_import(plan, staging)
        operations: list[FileOperation] = []
        for source in sorted(item for item in staging.rglob("*") if item.is_file()):
            relative = source.relative_to(staging).as_posix()
            target = self.repository.root / relative
            operations.append(
                FileOperation(
                    kind="replace" if target.exists() else "add",
                    path=relative,
                    expected_before_sha256=sha256_file(target) if target.exists() else None,
                    expected_after_sha256=sha256_file(source),
                    content_source=str(source),
                )
            )
        if not operations:
            raise ConflictError("import plan has no changes")
        return service.create(reason=reason, operations=operations)

    @classmethod
    def initialize(
        cls,
        path: Path,
        *,
        name: str,
        description: str | None = None,
        initialize_git: bool = True,
    ) -> "SelfNomad":
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,127}", name):
            raise ValueError("name contains unsupported characters")
        path = path.resolve()
        if path.exists() and any(path.iterdir()):
            raise ConflictError(f"destination is not empty: {path}")
        path.mkdir(parents=True, exist_ok=True)
        for directory in (
            "memory/daily",
            "memory/knowledge",
            "skills",
            "workflows",
            "evals/cases",
            "evals/fixtures",
            "policy",
            ".self-nomad/audit",
        ):
            (path / directory).mkdir(parents=True, exist_ok=True)
        atomic_write_text(path / "self-nomad.yaml", manifest_template(name, description))
        atomic_write_text(path / "policy/policy.yaml", POLICY_TEMPLATE)
        atomic_write_text(path / ".gitignore", ".self-nomad.local.yaml\n")
        for relative, content in ARTIFACT_TEMPLATES.items():
            atomic_write_text(path / relative, content)
        for keep in (
            "memory/daily/.gitkeep",
            "memory/knowledge/.gitkeep",
            "skills/.gitkeep",
            "workflows/.gitkeep",
            "evals/cases/.gitkeep",
            "evals/fixtures/.gitkeep",
            ".self-nomad/audit/.gitkeep",
        ):
            atomic_write_text(path / keep, "")
        if initialize_git:
            environment = os.environ.copy()
            environment["GIT_TERMINAL_PROMPT"] = "0"
            subprocess.run(
                ["git", "init", "--quiet", "--initial-branch=main", "--", str(path)],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
                env=environment,
            )
            from self_nomad.git import GitBackend

            backend = GitBackend(path)
            backend.ensure_local_identity()
            backend.commit_all(path, "self-nomad: initial self repository")
        return cls(SelfRepository(path))
