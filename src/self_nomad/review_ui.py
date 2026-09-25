"""Interactive proposal review. Approve and reject only — never apply."""

from __future__ import annotations

from uuid import UUID

from rich.console import Console
from rich.prompt import Prompt

from self_nomad.domain import ProposalRecord, ProposalStatus
from self_nomad.errors import ConflictError
from self_nomad.proposals import ProposalService
from self_nomad.render import render_review, render_simple

_ACTIONS = ("approve", "reject", "quit")


def _normalize_action(raw: str) -> str:
    value = raw.strip().lower()
    aliases = {"a": "approve", "r": "reject", "q": "quit"}
    return aliases.get(value, value)


def run_interactive_review(
    console: Console,
    service: ProposalService,
    record: ProposalRecord,
    *,
    identifier: str | None,
    diff: str,
) -> ProposalRecord:
    """Prompt for approve / reject / quit. Never calls apply."""
    status = record.status
    if status in {
        ProposalStatus.APPLIED,
        ProposalStatus.REJECTED,
        ProposalStatus.STALE,
        ProposalStatus.FAILED,
    }:
        render_simple(
            console,
            "review",
            f"Proposal is {status}; interactive actions are not available.",
            ok=False,
        )
        return record

    render_review(console, record, diff=diff, interactive_hint=True)
    action = _normalize_action(
        Prompt.ask("Action [approve/reject/quit]", default="quit", console=console)
    )
    if action not in _ACTIONS:
        raise ConflictError("action must be approve, reject, or quit")
    if action == "quit":
        render_simple(console, "review", "No change.", ok=True)
        return record
    if action == "reject":
        reason = Prompt.ask("Rejection reason", console=console).strip()
        if not reason:
            raise ConflictError("rejection reason is required")
        updated = service.reject(record.proposal.id, reason)
        render_simple(console, "reject", f"Rejected proposal {updated.proposal.id}.", ok=False)
        return updated

    # approve — validate first when the proposal is only materialized
    if record.status is ProposalStatus.MATERIALIZED:
        record = service.validate(record.proposal.id)
        render_simple(console, "validate", f"Proposal {record.proposal.id} is validated.")
    if record.status is ProposalStatus.APPROVED:
        render_simple(
            console,
            "review",
            "Already approved. Apply remains a separate command.",
        )
        return record
    approval_id = identifier
    if not approval_id:
        approval_id = Prompt.ask("Approval identifier", console=console).strip() or None
    updated = service.approve(record.proposal.id, approval_id)
    render_simple(
        console,
        "approve",
        f"Approved proposal {updated.proposal.id}. Apply remains a separate command.",
    )
    return updated


def review_record(
    service: ProposalService,
    proposal_id: UUID,
) -> tuple[ProposalRecord, str]:
    record = service.store.load(proposal_id)
    return record, service.unified_diff(proposal_id)
