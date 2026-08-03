"""Sanitize proposal and intake payloads for MCP clients."""

from __future__ import annotations

import base64
import json
from typing import Any
from uuid import UUID

from self_nomad.domain import ProposalRecord, ProposalStatus


def suggested_next_for_status(
    status: ProposalStatus,
    *,
    proposal_id: str | None = None,
) -> list[dict[str, str]]:
    """Capability-aware next steps for a proposal at the MCP boundary.

    MCP-callable actions use exact tool names. Operator-only lifecycle steps
    are labeled as CLI operations and are never implied to exist on this server.
    """
    pid = proposal_id or "PROPOSAL_ID"
    if status is ProposalStatus.MATERIALIZED:
        return [
            {
                "channel": "mcp",
                "tool": "self_nomad_proposal_validate",
                "description": "Strictly validate this proposal via MCP",
            },
            {
                "channel": "cli",
                "command": f"self-nomad review {pid}",
                "description": "Operator review of the isolated proposal (CLI)",
            },
            {
                "channel": "cli_operator",
                "command": f"self-nomad approve {pid}",
                "description": "Operator approval through the CLI",
            },
            {
                "channel": "cli_operator",
                "command": f"self-nomad apply {pid}",
                "description": "Operator apply through the CLI",
            },
        ]
    if status is ProposalStatus.VALIDATED:
        return [
            {
                "channel": "cli_operator",
                "command": f"self-nomad approve {pid}",
                "description": "Operator approval through the CLI",
            },
            {
                "channel": "cli_operator",
                "command": f"self-nomad apply {pid}",
                "description": "Operator apply through the CLI",
            },
        ]
    if status is ProposalStatus.APPROVED:
        return [
            {
                "channel": "cli_operator",
                "command": f"self-nomad apply {pid}",
                "description": "Operator apply through the CLI",
            },
        ]
    # Terminal or non-actionable states (applied, rejected, stale, failed, draft).
    return []


def suggested_next_for_intake(
    *,
    eligible: bool,
    existing_status: ProposalStatus | str | None = None,
    proposal_id: str | None = None,
) -> list[dict[str, str]]:
    """Structured next actions for intake preview/submit results."""
    status: ProposalStatus | None = None
    if isinstance(existing_status, ProposalStatus):
        status = existing_status
    elif isinstance(existing_status, str):
        try:
            status = ProposalStatus(existing_status)
        except ValueError:
            status = None

    if status is not None:
        return suggested_next_for_status(status, proposal_id=proposal_id)
    if eligible:
        return [
            {
                "channel": "mcp",
                "tool": "self_nomad_intake_submit",
                "description": "Submit this eligible request",
            }
        ]
    # Ineligible preview: no executable MCP action.
    return []


def sanitize_intake_preview(payload: dict[str, Any]) -> dict[str, Any]:
    """Rewrite core list[str] suggested_next into structured MCP actions."""
    result = dict(payload)
    eligible = bool(result.get("eligible"))
    existing = result.get("existing_status")
    existing_id = result.get("existing_proposal_id")
    result["suggested_next"] = suggested_next_for_intake(
        eligible=eligible,
        existing_status=existing,
        proposal_id=str(existing_id) if existing_id else None,
    )
    return result


def sanitize_intake_submit(payload: dict[str, Any]) -> dict[str, Any]:
    """Rewrite core list[str] suggested_next into structured MCP actions."""
    result = dict(payload)
    status = result.get("status")
    proposal_id = result.get("proposal_id")
    if isinstance(status, str):
        try:
            status_enum = ProposalStatus(status)
        except ValueError:
            result["suggested_next"] = []
            return result
        result["suggested_next"] = suggested_next_for_status(
            status_enum,
            proposal_id=str(proposal_id) if proposal_id else None,
        )
    else:
        result["suggested_next"] = []
    return result


def sanitize_proposal(record: ProposalRecord) -> dict[str, Any]:
    """Return a review-safe proposal payload without paths or content."""
    proposal = record.proposal
    operations = [
        {
            "kind": operation.kind,
            "path": operation.path,
            "expected_before_sha256": operation.expected_before_sha256,
            "expected_after_sha256": operation.expected_after_sha256,
        }
        for operation in proposal.operations
    ]
    payload: dict[str, Any] = {
        "proposal_id": str(proposal.id),
        "status": record.status.value,
        "created_at": proposal.created_at.isoformat(),
        "reason": proposal.reason,
        "risk": proposal.risk,
        "base_commit": proposal.base_commit,
        "target_branch": proposal.target_branch,
        "proposer": proposal.proposer.model_dump(mode="json"),
        "source_adapter": proposal.source_adapter,
        "operations": operations,
        "content_digest": record.content_digest,
        "validated_tree": record.validated_tree,
        "approved_tree": record.approved_tree,
        "approved_at": record.approved_at.isoformat() if record.approved_at else None,
        "approval_identifier": record.approval_identifier,
        "applied_commit": record.applied_commit,
        "rejection_reason": record.rejection_reason,
        "suggested_next": suggested_next_for_status(
            record.status, proposal_id=str(proposal.id)
        ),
    }
    if record.intake is not None:
        payload["intake"] = record.intake.model_dump(mode="json")
    return payload


def encode_cursor(proposal_id: UUID) -> str:
    raw = json.dumps({"after": proposal_id.hex}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str) -> str:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
        after = data["after"]
        if not isinstance(after, str) or len(after) != 32:
            raise ValueError("invalid cursor")
        return after
    except (KeyError, ValueError, json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError("invalid pagination cursor") from exc
