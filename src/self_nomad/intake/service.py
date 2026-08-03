"""Preview and durable submission for agent proposal intake."""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from uuid import UUID

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
    IntakeSubmissionFailedError,
    SelfNomadError,
)
from self_nomad.filesystem import contained_path, sha256_file
from self_nomad.git import GitBackend
from self_nomad.intake.models import ProposalRequest
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


class IntakeService:
    def __init__(
        self,
        repository: SelfRepository,
        *,
        state_root: Path | None = None,
        git: GitBackend | None = None,
    ) -> None:
        self.repository = repository
        self.git = git or GitBackend(repository.root)
        self.proposal_store = ProposalStore(repository.root, state_root)
        self.proposals = ProposalService(
            repository, state_root=state_root, git=self.git, store=self.proposal_store
        )
        self.store = IntakeStore(self.proposal_store)

    def _load_policy(self) -> Policy:
        manifest = self.repository.load_manifest()
        return Policy.model_validate(
            load_yaml(contained_path(self.repository.root, manifest.policy, must_exist=True))
        )

    def _resolve_branch(self, request: ProposalRequest) -> str:
        return request.target_branch or self.git.current_branch()

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
            if (
                operation.expected_after_sha256 is not None
                and digest is not None
                and operation.expected_after_sha256 != digest
            ):
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
                    expected_before_sha256=operation.expected_before_sha256,
                    expected_after_sha256=operation.expected_after_sha256 or digest,
                )
            )
        return summaries

    def _secret_findings(
        self, request: ProposalRequest, *, policy: Policy
    ) -> list[Finding]:
        if not policy.validation.scan_for_secrets:
            return []
        findings: list[Finding] = []
        # Scan operation content.
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
        # Scan provenance text for the same high-confidence patterns.
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
        # Before-hash soft checks against the live repository (preview only).
        for operation in request.operations:
            if operation.kind == "delete" or operation.expected_before_sha256 is None:
                continue
            target = self.repository.root / operation.path
            if not target.is_file():
                findings.append(
                    Finding(
                        severity="error",
                        code="INTAKE_BEFORE_MISSING",
                        message="expected file is missing for before-hash check",
                        path=operation.path,
                    )
                )
                continue
            if sha256_file(target) != operation.expected_before_sha256:
                findings.append(
                    Finding(
                        severity="error",
                        code="INTAKE_BEFORE_MISMATCH",
                        message="expected_before_sha256 does not match repository content",
                        path=operation.path,
                    )
                )
        risk = classify_proposal_risk(request.operations)
        digest = request.canonical_digest()
        existing_id: UUID | None = None
        existing_status: ProposalStatus | None = None
        receipt = self.store.load_receipt(request.request_id)
        if receipt is not None and receipt.status == "completed" and receipt.proposal_id:
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
        with FileLock(self.store.lock_path, timeout=30):
            receipt = self.store.load_receipt(request.request_id)
            if receipt is not None:
                if receipt.request_digest != digest:
                    raise IntakeIdConflictError(
                        "request_id was reused with a different payload",
                        code="INTAKE_ID_CONFLICT",
                    )
                if receipt.status == "completed" and receipt.proposal_id is not None:
                    record = self.proposal_store.load(receipt.proposal_id)
                    return self._submit_result(
                        request,
                        preview,
                        record,
                        reused=True,
                    )
                if receipt.status == "pending" and receipt.proposal_id is not None:
                    # Crash recovery: proposal was created; complete the receipt.
                    try:
                        record = self.proposal_store.load(receipt.proposal_id)
                    except SelfNomadError as exc:
                        raise IntakeSubmissionFailedError(
                            "interrupted submission is not recoverable",
                            code="INTAKE_SUBMISSION_FAILED",
                        ) from exc
                    receipt.status = "completed"
                    receipt.error = None
                    self.store.save_receipt(receipt)
                    self.store.clear_staging(digest)
                    return self._submit_result(request, preview, record, reused=True)
                if receipt.status == "failed":
                    # Allow retry of a failed attempt with the same payload.
                    pass
                elif receipt.status == "pending" and receipt.proposal_id is None:
                    # Resume incomplete staging/materialization for same digest.
                    pass

            # Register durable intent before materialization.
            receipt = IntakeReceipt(
                request_id=request.request_id,
                request_digest=digest,
                status="pending",
            )
            self.store.save_receipt(receipt)
            try:
                operations = self._stage_operations(request, digest=digest)
                provenance = IntakeProvenance(
                    request_id=request.request_id,
                    request_digest=digest,
                    runtime=request.source.runtime,
                    agent_identifier=request.source.agent_identifier,
                    correlation_id=request.source.correlation_id,
                )
                record = self.proposals.create(
                    reason=request.reason,
                    operations=operations,
                    target_branch=preview.target_branch,
                    proposer=Proposer(type="agent", identifier=request.source.agent_identifier),
                    source_adapter=request.source.runtime,
                    intake=provenance,
                )
                receipt.status = "completed"
                receipt.proposal_id = record.proposal.id
                receipt.error = None
                self.store.save_receipt(receipt)
                self.store.clear_staging(digest)
                return self._submit_result(request, preview, record, reused=False)
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

    def _stage_operations(
        self, request: ProposalRequest, *, digest: str
    ) -> list[FileOperation]:
        operations: list[FileOperation] = []
        for index, operation in enumerate(request.operations):
            content_source: str | None = None
            after = operation.expected_after_sha256
            if operation.content is not None:
                data = operation.content_bytes()
                assert data is not None
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
                    expected_before_sha256=operation.expected_before_sha256,
                    expected_after_sha256=after,
                    content_source=content_source,
                )
            )
        return operations

    def _submit_result(
        self,
        request: ProposalRequest,
        preview: IntakePreviewResult,
        record: ProposalRecord,
        *,
        reused: bool,
    ) -> IntakeSubmitResult:
        return IntakeSubmitResult(
            request_id=request.request_id,
            request_digest=preview.request_digest,
            reused=reused,
            proposal_id=record.proposal.id,
            status=record.status,
            risk=record.proposal.risk,
            operations=preview.operations,
            suggested_next=self._suggested_next(record.status, eligible=True),
        )
