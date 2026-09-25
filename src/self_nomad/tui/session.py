"""TUI operations. Every call goes through SelfNomad or a registered adapter."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from self_nomad.adapters import default_registry
from self_nomad.application import SelfNomad
from self_nomad.domain import Fidelity, ProposalRecord, ProposalStatus, RuntimeRef, TransferPlan
from self_nomad.errors import ConflictError, ValidationFailedError
from self_nomad.snapshot.models import PackSummary


class TuiSession:
    def __init__(self, repo: Path) -> None:
        self.nomad = SelfNomad.open(repo)

    @property
    def root(self) -> Path:
        return self.nomad.repository.root

    def home_status(self) -> dict[str, str]:
        result = self.nomad.repository.validate(strict=False)
        user = self.root / "identity" / "user.md"
        daily = self.root / "memory" / "daily"
        daily_files = daily.is_dir() and any(path.is_file() for path in daily.rglob("*"))
        if user.is_file() or daily_files:
            hint = (
                "working tree has identity/user.md or memory/daily; "
                "specialist packs omit them"
            )
        else:
            hint = "no user profile or daily memory in the working tree"
        return {
            "root": str(self.root),
            "valid": "yes" if result.valid else "no",
            "digest": result.content_digest,
            "hint": hint,
        }

    def detect_lines(self, hint: Path | None) -> list[str]:
        registry = default_registry()
        lines: list[str] = []
        for name in registry.names():
            found = registry.get(name).detect(hint)
            if not found.candidates:
                lines.append(f"{name}: no candidates")
                continue
            for candidate in found.candidates:
                lines.append(f"{name}: {candidate.root}")
        return lines

    def preview_import(self, adapter_name: str, runtime_path: Path) -> TransferPlan:
        adapter = default_registry().get(adapter_name)
        found = adapter.detect(runtime_path)
        if len(found.candidates) != 1:
            raise ConflictError(
                f"{adapter_name} detect returned {len(found.candidates)} candidates; "
                "pass the runtime directory"
            )
        return adapter.plan_import(found.candidates[0], self.nomad.repository)

    def confirm_import(self, plan: TransferPlan) -> ProposalRecord:
        return self.nomad.create_import_proposal(plan, reason="Import from TUI")

    def proposal_lines(self) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        for record in self.nomad.proposals().list_records():
            label = f"{record.proposal.id} {record.status} {record.proposal.reason}"
            rows.append((label, str(record.proposal.id)))
        return rows

    def diff(self, proposal_id: UUID) -> str:
        return self.nomad.proposals().unified_diff(proposal_id)

    def approve(self, proposal_id: UUID, identifier: str) -> ProposalRecord:
        cleaned = identifier.strip()
        if not cleaned:
            raise ConflictError("approval identifier is required")
        service = self.nomad.proposals()
        record = _find_record(service.list_records(), proposal_id)
        if record.status is ProposalStatus.MATERIALIZED:
            service.validate(proposal_id)
        return service.approve(proposal_id, identifier=cleaned)

    def reject(self, proposal_id: UUID, reason: str) -> ProposalRecord:
        cleaned = reason.strip()
        if not cleaned:
            raise ConflictError("rejection reason is required")
        return self.nomad.proposals().reject(proposal_id, cleaned)

    def apply(self, proposal_id: UUID) -> ProposalRecord:
        return self.nomad.proposals().apply(proposal_id)

    def pack(self, destination: Path, *, profile: str, include_long_term: bool) -> PackSummary:
        return self.nomad.pack(
            destination,
            profile=profile,
            include_long_term_memory=include_long_term,
        )

    def check_pack(self, archive: Path, *, profile: str = "specialist") -> PackSummary:
        return SelfNomad.check_pack(archive, profile=profile)

    def install_pack(self, archive: Path, destination: Path) -> PackSummary:
        _installed, summary = SelfNomad.install_pack(archive, destination, initialize_git=False)
        return summary

    def preview_restore(self, adapter_name: str, target: Path) -> TransferPlan:
        adapter = default_registry().get(adapter_name)
        runtime = RuntimeRef(adapter=adapter_name, root=target, name=target.name)
        return adapter.plan_restore(self.nomad.repository, runtime)

    def apply_restore(self, plan: TransferPlan) -> list[str]:
        adapter = default_registry().get(plan.adapter)
        validation = adapter.validate(self.nomad.repository, plan.runtime)
        if not validation.valid:
            raise ValidationFailedError("adapter validation failed")
        result = adapter.apply_restore(plan)
        return [path.as_posix() for path in result.written]


def format_plan(plan: TransferPlan) -> str:
    lines = [f"{plan.adapter} {plan.direction}"]
    for item in plan.mappings:
        lines.append(
            f"map {item.artifact} {item.fidelity.value} {item.action} {item.reason or ''}".rstrip()
        )
    for item in plan.exclusions:
        lines.append(
            f"exclude {item.artifact} {item.fidelity.value} {item.reason or ''}".rstrip()
        )
    flagged = {Fidelity.ADAPTED, Fidelity.UNSUPPORTED}
    visible = [*plan.mappings, *plan.exclusions]
    if any(item.fidelity in flagged for item in visible):
        lines.append("adapted or unmapped classes are listed above")
    return "\n".join(lines)


def _find_record(records: list[ProposalRecord], proposal_id: UUID) -> ProposalRecord:
    for record in records:
        if record.proposal.id == proposal_id:
            return record
    raise ConflictError(f"proposal not found: {proposal_id}")
