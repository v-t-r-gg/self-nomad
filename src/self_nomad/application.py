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
    from self_nomad.proposals import ProposalService


class SelfNomad:
    def __init__(self, repository: SelfRepository) -> None:
        self.repository = repository

    @classmethod
    def open(cls, path: Path) -> "SelfNomad":
        return cls(SelfRepository.discover(path))

    def proposals(self, *, state_root: Path | None = None) -> "ProposalService":
        from self_nomad.proposals import ProposalService

        return ProposalService(self.repository, state_root=state_root)

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
                ["git", "init", "--quiet", "--", str(path)],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
                env=environment,
            )
        return cls(SelfRepository(path))
