"""Sanitize proposal and status payloads for MCP clients."""

from __future__ import annotations

import base64
import json
from typing import Any
from uuid import UUID

from self_nomad.domain import ProposalRecord, ProposalStatus


def suggested_next_for_status(status: ProposalStatus) -> list[str]:
    if status is ProposalStatus.MATERIALIZED:
        return ["validate", "review", "approve", "apply"]
    if status is ProposalStatus.VALIDATED:
        return ["approve", "apply"]
    if status is ProposalStatus.APPROVED:
        return ["apply"]
    return []


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
        "suggested_next": suggested_next_for_status(record.status),
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
