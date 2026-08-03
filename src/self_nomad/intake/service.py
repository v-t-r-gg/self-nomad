"""Preview and durable submission for agent proposal intake."""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from filelock import FileLock
from pydantic import BaseModel, ConfigDict, Field

from self_nomad.domain import (
    FileOperation,
    Finding,
    IntakeProvenance,
    ProposalRecord,
    ProposalStatus,
    Proposer,
)
from self_nomad.errors import (
    IntakeContentTooLargeError,
    IntakeContentUnsafeError,
    IntakeIdConflictError,
    IntakePolicyRejectedError,
    IntakeRequestTooLargeError,
    IntakeSubmissionFailedError,
    ProposalNotFoundError,
    SelfNomadError,
)
from self_nomad.filesystem import contained_path, sha256_file
from self_nomad.git import GitBackend
from self_nomad.intake.models import (
    AddOperation,
    DeleteOperation,
    ProposalRequest,
    ReplaceOperation,
)
from self_nomad.intake.store import IntakeReceipt, IntakeStore
from self_nomad.manifest.loader import load_yaml
from self_nomad.policy import Policy
from self_nomad.proposals.risk import classify_proposal_risk
from self_nomad.proposals.service import ProposalService
from self_nomad.proposals.store import ProposalStore
from self_nomad.repository import SelfRepository


class OperationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["add", "replace", "delete"]
    path: str
    utf8_byte_count: int = 0
    content_sha256: str | None = None
    expected_before_sha256: str | None = None
    expected_after_sha256: str | None = None


class IntakePreviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    request_id: str
    request_digest: str
    repository_id: UUID
    base_commit: str
    target_branch: str
    risk: Literal["low", "medium", "high", "critical"]
    operations: list[OperationSummary]
    findings: list[Finding] = Field(default_factory=list)
    eligible: bool
    existing_proposal_id: UUID | None = None
    existing_status: ProposalStatus | None = None
    suggested_next: list[str] = Field(default_factory=list)


class IntakeSubmitResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    request_id: str
    request_digest: str
    reused: bool
    proposal_id: UUID
    status: ProposalStatus
    risk: Literal["low", "medium", "high", "critical"]
    operations: list[OperationSummary]
    suggested_next: list[str] = Field(default_factory=list)


class InjectedCrash(RuntimeError):
    """Test-only process-crash simulation; leaves receipt unrecovered."""


class IntakeService:
    def __init__(
        self,
        repository: SelfRepository,
        *,
        state_root: Path | None = None,
        git: GitBackend | None = None,
        fault_after: str | None = None,
    ) -> None:
        self.repository = repository
        self.git = git or GitBackend(repository.root)
        self.proposal_store = ProposalStore(repository.root, state_root)
        self.proposals = ProposalService(
            repository, state_root=state_root, git=self.git, store=self.proposal_store
        )
        self.store = IntakeStore(self.proposal_store)
        # Test-only injection points for crash-window coverage.
        self._fault_after = fault_after

    def _checkpoint(self, name: str) -> None:
        if self._fault_after == name:
            raise InjectedCrash(f"injected fault after {name}")

    def _load_policy(self) -> Policy:
        manifest = self.repository.load_manifest()
        return Policy.model_validate(
            load_yaml(contained_path(self.repository.root, manifest.policy, must_exist=True))
        )

    def _resolve_branch(self, request: ProposalRequest) -> str:
        return request.target_branch or self.git.current_branch()

    def _enforce_request_size(self, request: ProposalRequest, policy: Policy) -> None:
        size = len(request.canonical_bytes())
        if size > policy.limits.maximum_request_bytes:
            raise IntakeRequestTooLargeError(
                f"request exceeds maximum_request_bytes ({policy.limits.maximum_request_bytes})",
                code="INTAKE_REQUEST_TOO_LARGE",
            )

    def _operation_summaries(
        self, request: ProposalRequest, *, policy: Policy
    ) -> list[OperationSummary]:
        summaries: list[OperationSummary] = []
        for operation in request.operations:
            data = operation.content_bytes()
            size = len(data) if data is not None else 0
            if data is not None and size > policy.limits.maximum_file_bytes:
                raise IntakeContentTooLargeError(
                    f"content exceeds maximum_file_bytes for {operation.path}",
                    code="INTAKE_CONTENT_TOO_LARGE",
                )
            digest = operation.content_sha256()
            expected_after = getattr(operation, "expected_after_sha256", None)
            if expected_after is not None and digest is not None and expected_after != digest:
                raise IntakeContentUnsafeError(
                    f"expected_after_sha256 does not match content for {operation.path}",
                    code="INTAKE_CONTENT_UNSAFE",
                )
            summaries.append(
                OperationSummary(
                    kind=operation.kind,
                    path=operation.path,
                    utf8_byte_count=size,
                    content_sha256=digest,
                    expected_before_sha256=getattr(operation, "expected_before_sha256", None),
                    expected_after_sha256=expected_after or digest,
                )
            )
        return summaries

    def _secret_findings(
        self, request: ProposalRequest, *, policy: Policy
    ) -> list[Finding]:
        if not policy.validation.scan_for_secrets:
            return []
        findings: list[Finding] = []
        for operation in request.operations:
            data = operation.content_bytes()
            if data is None:
                continue
            if any(pattern.search(data) for pattern in SelfRepository.SECRET_PATTERNS):
                findings.append(
                    Finding(
                        severity="blocker",
                        code="SN1302",
                        message="high-confidence secret pattern detected",
                        path=operation.path,
                    )
                )
        provenance_bits = [
            request.request_id,
            request.reason,
            request.source.runtime,
            request.source.agent_identifier or "",
            request.source.correlation_id or "",
        ]
        provenance_blob = "\n".join(provenance_bits).encode("utf-8")
        if any(pattern.search(provenance_blob) for pattern in SelfRepository.SECRET_PATTERNS):
            findings.append(
                Finding(
                    severity="blocker",
                    code="SN1302",
                    message="high-confidence secret pattern detected in provenance",
                    path=None,
                )
            )
        return findings

    def _target_tree_findings(
        self, request: ProposalRequest, *, base_commit: str
    ) -> list[Finding]:
        findings: list[Finding] = []
        seen: set[str] = set()
        for operation in request.operations:
            if operation.path in seen:
                findings.append(
                    Finding(
                        severity="error",
                        code="INTAKE_DUPLICATE_PATH",
                        message="duplicate operation path in request",
                        path=operation.path,
                    )
                )
                continue
            seen.add(operation.path)
            entry = self.git.path_at_commit(base_commit, operation.path)
            if entry.kind == "symlink":
                findings.append(
                    Finding(
                        severity="blocker",
                        code="INTAKE_TARGET_SYMLINK",
                        message="target path is a symbolic link in the target commit",
                        path=operation.path,
                    )
                )
                continue
            if entry.kind in {"tree", "other"}:
                findings.append(
                    Finding(
                        severity="error",
                        code="INTAKE_TARGET_UNSUPPORTED",
                        message="target path is not a regular blob in the target commit",
                        path=operation.path,
                    )
                )
                continue
            if isinstance(operation, AddOperation):
                if entry.kind != "missing":
                    findings.append(
                        Finding(
                            severity="error",
                            code="INTAKE_ADD_EXISTS",
                            message="add target already exists on the target branch",
                            path=operation.path,
                        )
                    )
                continue
            if isinstance(operation, ReplaceOperation | DeleteOperation):
                if entry.kind == "missing":
                    findings.append(
                        Finding(
                            severity="error",
                            code="INTAKE_TARGET_MISSING",
                            message="replace/delete target is missing on the target branch",
                            path=operation.path,
                        )
                    )
                    continue
                if entry.kind != "blob" or entry.sha256 is None:
                    findings.append(
                        Finding(
                            severity="error",
                            code="INTAKE_TARGET_UNSUPPORTED",
                            message="target path is not a regular blob in the target commit",
                            path=operation.path,
                        )
                    )
                    continue
                if (
                    operation.expected_before_sha256 is not None
                    and operation.expected_before_sha256 != entry.sha256
                ):
                    findings.append(
                        Finding(
                            severity="error",
                            code="INTAKE_BEFORE_MISMATCH",
                            message="expected_before_sha256 does not match target-branch blob",
                            path=operation.path,
                        )
                    )
        return findings

    def _suggested_next(self, status: ProposalStatus | None, *, eligible: bool) -> list[str]:
        if status is ProposalStatus.MATERIALIZED:
            return ["validate", "review", "approve", "apply"]
        if status is ProposalStatus.VALIDATED:
            return ["approve", "apply"]
        if status is ProposalStatus.APPROVED:
            return ["apply"]
        if status in {
            ProposalStatus.APPLIED,
            ProposalStatus.REJECTED,
            ProposalStatus.STALE,
            ProposalStatus.FAILED,
        }:
            return []
        if eligible:
            return ["submit"]
        return []

    def preview(self, request: ProposalRequest) -> IntakePreviewResult:
        policy = self._load_policy()
        self._enforce_request_size(request, policy)
        if len(request.operations) > policy.limits.maximum_proposal_files:
            raise IntakePolicyRejectedError(
                "request exceeds maximum_proposal_files",
                code="INTAKE_POLICY_REJECTED",
            )
        manifest = self.repository.load_manifest()
        branch = self._resolve_branch(request)
        base_commit = self.git.head(f"refs/heads/{branch}")
        summaries = self._operation_summaries(request, policy=policy)
        findings = self._secret_findings(request, policy=policy)
        findings.extend(self._target_tree_findings(request, base_commit=base_commit))
        risk = classify_proposal_risk(request.operations)
        digest = request.canonical_digest()
        existing_id: UUID | None = None
        existing_status: ProposalStatus | None = None
        receipt = self.store.load_receipt(request.request_id)
        if receipt is not None and receipt.status == "completed":
            try:
                record = self.proposal_store.load(receipt.proposal_id)
                existing_id = record.proposal.id
                existing_status = record.status
            except SelfNomadError:
                existing_id = receipt.proposal_id
        invalid = {"error", "blocker"}
        eligible = not any(item.severity in invalid for item in findings)
        return IntakePreviewResult(
            request_id=request.request_id,
            request_digest=digest,
            repository_id=manifest.self.id,
            base_commit=base_commit,
            target_branch=branch,
            risk=risk,
            operations=summaries,
            findings=findings,
            eligible=eligible,
            existing_proposal_id=existing_id,
            existing_status=existing_status,
            suggested_next=self._suggested_next(existing_status, eligible=eligible),
        )

    def submit(self, request: ProposalRequest) -> IntakeSubmitResult:
        preview = self.preview(request)
        if not preview.eligible:
            blockers = [
                f"{item.code}: {item.message}"
                for item in preview.findings
                if item.severity in {"error", "blocker"}
            ]
            raise IntakePolicyRejectedError(
                "; ".join(blockers) or "request rejected by policy",
                code="INTAKE_POLICY_REJECTED",
            )
        digest = preview.request_digest
        # Ensure lock parent exists only when submitting (durable path).
        self.store.ensure_writable()
        with FileLock(self.store.lock_path, timeout=30):
            return self._submit_locked(request, preview, digest)

    def _submit_locked(
        self,
        request: ProposalRequest,
        preview: IntakePreviewResult,
        digest: str,
    ) -> IntakeSubmitResult:
        receipt = self.store.load_receipt(request.request_id)
        if receipt is not None:
            if receipt.request_digest != digest:
                raise IntakeIdConflictError(
                    "request_id was reused with a different payload",
                    code="INTAKE_ID_CONFLICT",
                )
            return self._resume_or_complete(request, preview, receipt)

        proposal_id = uuid4()
        receipt = IntakeReceipt(
            request_id=request.request_id,
            request_digest=digest,
            status="pending",
            proposal_id=proposal_id,
        )
        self.store.save_receipt(receipt)
        self._checkpoint("pending_receipt")
        return self._execute_submission(request, preview, receipt)

    def _resume_or_complete(
        self,
        request: ProposalRequest,
        preview: IntakePreviewResult,
        receipt: IntakeReceipt,
    ) -> IntakeSubmitResult:
        proposal_id = receipt.proposal_id
        if receipt.status == "completed":
            record = self.proposal_store.load(proposal_id)
            self.store.clear_staging(receipt.request_digest)
            return self._submit_result(preview, record, reused=True)

        if receipt.status == "failed":
            raise IntakeSubmissionFailedError(
                f"prior submission for proposal {proposal_id} failed"
                + (f": {receipt.error}" if receipt.error else ""),
                code="INTAKE_SUBMISSION_FAILED",
            )

        # pending
        try:
            record = self.proposal_store.load(proposal_id)
        except ProposalNotFoundError:
            # Crash after receipt, before draft: create reserved proposal.
            return self._execute_submission(request, preview, receipt)

        if record.status is ProposalStatus.DRAFT:
            return self._materialize_and_complete(
                request, preview, receipt, record, reused=True
            )
        if record.status is ProposalStatus.FAILED:
            raise IntakeSubmissionFailedError(
                f"proposal {proposal_id} is failed; request_id is reserved",
                code="INTAKE_SUBMISSION_FAILED",
            )
        # Materialized or later: complete receipt and reuse.
        receipt.status = "completed"
        receipt.error = None
        self.store.save_receipt(receipt)
        self.store.clear_staging(receipt.request_digest)
        return self._submit_result(preview, record, reused=True)

    def _execute_submission(
        self,
        request: ProposalRequest,
        preview: IntakePreviewResult,
        receipt: IntakeReceipt,
    ) -> IntakeSubmitResult:
        try:
            operations = self._stage_operations(request, digest=receipt.request_digest)
            self._checkpoint("staging")
            provenance = IntakeProvenance(
                request_id=request.request_id,
                request_digest=receipt.request_digest,
                runtime=request.source.runtime,
                agent_identifier=request.source.agent_identifier,
                correlation_id=request.source.correlation_id,
            )
            record = self.proposals.create_draft(
                reason=request.reason,
                operations=operations,
                target_branch=preview.target_branch,
                proposer=Proposer(type="agent", identifier=request.source.agent_identifier),
                source_adapter=request.source.runtime,
                intake=provenance,
                proposal_id=receipt.proposal_id,
            )
            self._checkpoint("proposal_record")
            return self._materialize_and_complete(
                request, preview, receipt, record, reused=False
            )
        except InjectedCrash:
            # Simulate hard process exit: durable pending state remains as-is.
            raise
        except IntakeIdConflictError:
            raise
        except Exception as exc:
            receipt.status = "failed"
            receipt.error = type(exc).__name__
            self.store.save_receipt(receipt)
            if isinstance(exc, SelfNomadError):
                raise IntakeSubmissionFailedError(
                    str(exc),
                    code="INTAKE_SUBMISSION_FAILED",
                ) from exc
            raise IntakeSubmissionFailedError(
                "intake submission failed",
                code="INTAKE_SUBMISSION_FAILED",
            ) from exc

    def _materialize_and_complete(
        self,
        request: ProposalRequest,
        preview: IntakePreviewResult,
        receipt: IntakeReceipt,
        record: ProposalRecord,
        *,
        reused: bool,
    ) -> IntakeSubmitResult:
        try:
            if record.status is ProposalStatus.DRAFT:
                record = self.proposals.materialize(record.proposal.id)
            self._checkpoint("materialized")
            self._checkpoint("before_completed_receipt")
            receipt.status = "completed"
            receipt.error = None
            self.store.save_receipt(receipt)
            self._checkpoint("completed_receipt")
            self.store.clear_staging(receipt.request_digest)
            return self._submit_result(preview, record, reused=reused)
        except InjectedCrash:
            raise
        except Exception as exc:
            receipt.status = "failed"
            receipt.error = type(exc).__name__
            self.store.save_receipt(receipt)
            if isinstance(exc, SelfNomadError):
                raise IntakeSubmissionFailedError(
                    str(exc),
                    code="INTAKE_SUBMISSION_FAILED",
                ) from exc
            raise IntakeSubmissionFailedError(
                "intake submission failed",
                code="INTAKE_SUBMISSION_FAILED",
            ) from exc

    def _stage_operations(
        self, request: ProposalRequest, *, digest: str
    ) -> list[FileOperation]:
        operations: list[FileOperation] = []
        for index, operation in enumerate(request.operations):
            content_source: str | None = None
            after = getattr(operation, "expected_after_sha256", None)
            data = operation.content_bytes()
            if data is not None:
                staged = self.store.stage_content(digest, index, data)
                content_source = str(staged)
                computed = sha256_file(staged)
                if after is None:
                    after = computed
                elif after != computed:
                    raise IntakeContentUnsafeError(
                        f"expected_after_sha256 does not match content for {operation.path}",
                        code="INTAKE_CONTENT_UNSAFE",
                    )
            operations.append(
                FileOperation(
                    kind=operation.kind,
                    path=operation.path,
                    expected_before_sha256=getattr(operation, "expected_before_sha256", None),
                    expected_after_sha256=after,
                    content_source=content_source,
                )
            )
        return operations

    def _submit_result(
        self,
        preview: IntakePreviewResult,
        record: ProposalRecord,
        *,
        reused: bool,
    ) -> IntakeSubmitResult:
        return IntakeSubmitResult(
            request_id=preview.request_id,
            request_digest=preview.request_digest,
            reused=reused,
            proposal_id=record.proposal.id,
            status=record.status,
            risk=record.proposal.risk,
            operations=preview.operations,
            suggested_next=self._suggested_next(record.status, eligible=True),
        )
