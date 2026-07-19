import json
import shutil
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from filelock import FileLock

from self_nomad.domain import FileOperation, Proposal, ProposalRecord, ProposalStatus, Proposer
from self_nomad.errors import (
    ConflictError,
    ProposalStaleError,
    ProposalStateError,
    ValidationFailedError,
)
from self_nomad.filesystem import atomic_write_text, contained_path, sha256_file
from self_nomad.git import GitBackend
from self_nomad.manifest.loader import load_yaml
from self_nomad.policy import Policy
from self_nomad.repository import SelfRepository

from .store import ProposalStore


class ProposalService:
    def __init__(
        self,
        repository: SelfRepository,
        *,
        state_root: Path | None = None,
        git: GitBackend | None = None,
    ) -> None:
        self.repository = repository
        self.git = git or GitBackend(repository.root)
        self.store = ProposalStore(repository.root, state_root)

    def create(
        self,
        *,
        reason: str,
        operations: list[FileOperation],
        target_branch: str | None = None,
        proposer: Proposer | None = None,
    ) -> ProposalRecord:
        manifest = self.repository.load_manifest()
        policy = Policy.model_validate(
            load_yaml(contained_path(self.repository.root, manifest.policy, must_exist=True))
        )
        if len(operations) > policy.limits.maximum_proposal_files:
            raise ConflictError("proposal exceeds maximum_proposal_files")
        risk = self._classify_risk(operations)
        for operation in operations:
            if operation.content_source:
                source = Path(operation.content_source)
                if source.is_symlink() or not source.is_file():
                    raise ConflictError("content source must be a regular file")
                if source.stat().st_size > policy.limits.maximum_file_bytes:
                    raise ConflictError(
                        f"content source exceeds maximum_file_bytes: {operation.path}"
                    )
        branch = target_branch or self.git.current_branch()
        proposal = Proposal(
            repository_id=manifest.self.id,
            base_commit=self.git.head(f"refs/heads/{branch}"),
            target_branch=branch,
            proposer=proposer or Proposer(),
            reason=reason,
            operations=operations,
            risk=risk,
        )
        record = ProposalRecord(proposal=proposal)
        self.store.save(record)
        return self.materialize(proposal.id)

    @staticmethod
    def _classify_risk(
        operations: list[FileOperation],
    ) -> Literal["low", "medium", "high", "critical"]:
        paths = [operation.path for operation in operations]
        if any(
            path.startswith("policy/")
            or path == "self-nomad.yaml"
            or Path(path).suffix in {".py", ".sh", ".js", ".exe"}
            for path in paths
        ):
            return "critical"
        if any(
            operation.kind == "delete" or operation.path.startswith("identity/")
            for operation in operations
        ):
            return "high"
        if any(path.startswith("skills/") for path in paths):
            return "medium"
        return "low"

    def materialize(self, proposal_id: UUID) -> ProposalRecord:
        with FileLock(self.store.lock_path, timeout=10):
            record = self.store.load(proposal_id)
            if record.status is not ProposalStatus.DRAFT:
                raise ProposalStateError("only draft proposals can be materialized")
            worktree = self.store.worktrees / str(proposal_id)
            branch = f"self-nomad/proposal/{proposal_id}"
            try:
                self.git.worktree_add(worktree, branch, record.proposal.base_commit)
                self._apply_operations(record.proposal.operations, worktree)
                commit = self.git.commit_all(
                    worktree,
                    f"self-nomad(proposal): {record.proposal.reason}\n\n"
                    f"Self-Nomad-Proposal: {proposal_id}\n"
                    f"Self-Nomad-Base: {record.proposal.base_commit}\n"
                    f"Self-Nomad-Risk: {record.proposal.risk}",
                )
            except Exception:
                record.status = ProposalStatus.FAILED
                record.worktree = str(worktree)
                record.branch = branch
                self.store.save(record)
                raise
            record.status = ProposalStatus.MATERIALIZED
            record.worktree = str(worktree)
            record.branch = branch
            record.proposal_commit = commit
            self.store.save(record)
            return record

    def _apply_operations(self, operations: list[FileOperation], worktree: Path) -> None:
        seen: set[str] = set()
        for operation in operations:
            if operation.path in seen:
                raise ConflictError(f"duplicate operation path: {operation.path}")
            seen.add(operation.path)
            target = contained_path(worktree, operation.path)
            exists = target.exists()
            if operation.kind == "add" and exists:
                raise ConflictError(f"add target already exists: {operation.path}")
            if operation.kind in {"replace", "delete"} and not exists:
                raise ConflictError(f"target does not exist: {operation.path}")
            if exists and (target.is_symlink() or not target.is_file()):
                raise ConflictError(f"operation target must be a regular file: {operation.path}")
            if (
                exists
                and operation.expected_before_sha256
                and sha256_file(target) != operation.expected_before_sha256
            ):
                raise ProposalStaleError(f"before hash differs: {operation.path}")
            if operation.kind == "delete":
                target.unlink()
                continue
            source_input = Path(operation.content_source or "")
            if source_input.is_symlink() or not source_input.is_file():
                raise ConflictError("content source must be a regular file")
            source = source_input.resolve(strict=True)
            content = source.read_text(encoding="utf-8")
            atomic_write_text(target, content)
            if (
                operation.expected_after_sha256
                and sha256_file(target) != operation.expected_after_sha256
            ):
                raise ConflictError(f"after hash differs: {operation.path}")

    def validate(self, proposal_id: UUID) -> ProposalRecord:
        record = self.store.load(proposal_id)
        if record.status not in {ProposalStatus.MATERIALIZED, ProposalStatus.VALIDATED}:
            raise ProposalStateError("proposal must be materialized before validation")
        if record.worktree is None:
            raise ProposalStateError("proposal worktree is missing")
        self._verify_or_invalidate(record)
        result = SelfRepository(Path(record.worktree)).validate(strict=True)
        if not result.valid:
            raise ValidationFailedError(
                "; ".join(f"{finding.code}: {finding.message}" for finding in result.findings)
            )
        record.status = ProposalStatus.VALIDATED
        record.content_digest = result.content_digest
        record.validated_tree = self.git.tree(record.proposal_commit or "")
        record.approved_tree = None
        record.approved_at = None
        self.store.save(record)
        return record

    def approve(self, proposal_id: UUID, identifier: str | None = None) -> ProposalRecord:
        record = self.store.load(proposal_id)
        if record.status is not ProposalStatus.VALIDATED:
            raise ProposalStateError("proposal must be validated before approval")
        self._verify_or_invalidate(record)
        current_tree = self.git.tree(record.proposal_commit or "")
        if current_tree != record.validated_tree:
            raise ProposalStaleError("proposal tree changed after validation")
        record.status = ProposalStatus.APPROVED
        record.approved_tree = current_tree
        record.approved_at = datetime.now(UTC)
        record.approval_identifier = identifier
        self.store.save(record)
        return record

    def reject(self, proposal_id: UUID, reason: str) -> ProposalRecord:
        record = self.store.load(proposal_id)
        if record.status in {ProposalStatus.APPLIED, ProposalStatus.REJECTED}:
            raise ProposalStateError(f"cannot reject a {record.status} proposal")
        record.status = ProposalStatus.REJECTED
        record.rejection_reason = reason
        self.store.save(record)
        return record

    def apply(self, proposal_id: UUID) -> ProposalRecord:
        with FileLock(self.store.lock_path, timeout=10):
            record = self.store.load(proposal_id)
            if record.status is not ProposalStatus.APPROVED:
                raise ProposalStateError("proposal must be approved before application")
            proposal = record.proposal
            current = self.git.head(f"refs/heads/{proposal.target_branch}")
            if current != proposal.base_commit:
                record.status = ProposalStatus.STALE
                self.store.save(record)
                raise ProposalStaleError("target branch moved from the proposal base")
            if proposal.target_branch in self.git.checked_out_branches():
                raise ConflictError(
                    "target branch is checked out; switch that worktree to another branch "
                    "or detach HEAD"
                )
            if not record.worktree or not record.proposal_commit or not record.content_digest:
                raise ProposalStateError("proposal record is incomplete")
            worktree = Path(record.worktree)
            self._verify_or_invalidate(record)
            proposal_tree = self.git.tree(record.proposal_commit)
            if proposal_tree != record.validated_tree or proposal_tree != record.approved_tree:
                raise ProposalStaleError("approved proposal tree changed")
            validation = SelfRepository(worktree).validate(strict=True)
            if not validation.valid or validation.content_digest != record.content_digest:
                raise ProposalStaleError("validated proposal contents changed")
            audit_path = worktree / ".self-nomad/audit" / f"{proposal.id}.json"
            audit = {
                "schema_version": 1,
                "proposal_id": str(proposal.id),
                "base_commit": proposal.base_commit,
                "proposal_commit": record.proposal_commit,
                "applied_at": datetime.now(UTC).isoformat(),
                "proposer": proposal.proposer.model_dump(mode="json"),
                "reason": proposal.reason,
                "risk": proposal.risk,
                "content_digest": record.content_digest,
                "approval_identifier": record.approval_identifier,
                "operations": [
                    {
                        "kind": operation.kind,
                        "path": operation.path,
                        "expected_before_sha256": operation.expected_before_sha256,
                        "expected_after_sha256": operation.expected_after_sha256,
                    }
                    for operation in proposal.operations
                ],
            }
            atomic_write_text(audit_path, json.dumps(audit, indent=2, sort_keys=True) + "\n")
            audit_relative = audit_path.relative_to(worktree).as_posix()
            final_commit = self.git.commit_paths(
                worktree,
                f"self-nomad(audit): apply {proposal.id}\n\n"
                f"Self-Nomad-Proposal: {proposal.id}\n"
                f"Self-Nomad-Base: {proposal.base_commit}",
                [audit_relative],
            )
            if self.git.changed_paths(record.proposal_commit, final_commit) != {
                audit_relative: "A"
            }:
                raise ProposalStaleError(
                    "finalization commit contains changes beyond its audit record"
                )
            try:
                self.git.update_ref(proposal.target_branch, final_commit, proposal.base_commit)
            except Exception:
                record.status = ProposalStatus.STALE
                self.store.save(record)
                raise
            record.status = ProposalStatus.APPLIED
            record.applied_commit = final_commit
            self.store.save(record)
            return record

    def _verify_declared_tree(self, record: ProposalRecord) -> None:
        if not record.worktree or not record.proposal_commit:
            raise ProposalStateError("proposal record is incomplete")
        worktree = Path(record.worktree)
        actual_head = self.git.run("rev-parse", "HEAD", cwd=worktree).stdout.strip()
        if actual_head != record.proposal_commit:
            raise ProposalStaleError("worktree HEAD changed after materialization")
        if not self.git.is_clean(worktree):
            raise ProposalStaleError("proposal worktree has staged, unstaged, or untracked changes")
        expected_status = {"add": "A", "replace": "M", "delete": "D"}
        expected = {
            operation.path: expected_status[operation.kind]
            for operation in record.proposal.operations
        }
        actual = self.git.changed_paths(record.proposal.base_commit, record.proposal_commit)
        if actual != expected:
            raise ProposalStaleError("proposal commit does not exactly match declared operations")

    def _verify_or_invalidate(self, record: ProposalRecord) -> None:
        try:
            self._verify_declared_tree(record)
        except ProposalStaleError:
            record.status = ProposalStatus.MATERIALIZED
            record.content_digest = None
            record.validated_tree = None
            record.approved_tree = None
            record.approved_at = None
            record.approval_identifier = None
            self.store.save(record)
            raise

    def cleanup(self, proposal_id: UUID) -> None:
        record = self.store.load(proposal_id)
        terminal = {ProposalStatus.APPLIED, ProposalStatus.REJECTED, ProposalStatus.FAILED}
        if record.status not in terminal:
            raise ProposalStateError("only terminal proposal worktrees can be cleaned")
        if record.worktree and Path(record.worktree).exists():
            self.git.remove_worktree(Path(record.worktree))
        if record.branch:
            with suppress(Exception):
                self.git.run("branch", "-D", record.branch)
        if record.worktree:
            shutil.rmtree(record.worktree, ignore_errors=True)
