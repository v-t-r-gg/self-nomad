"""Agent-facing proposal intake."""

from self_nomad.intake.loader import (
    load_proposal_request,
    load_proposal_request_from_path,
    load_proposal_request_from_stream,
)
from self_nomad.intake.models import IntakeOperation, IntakeSource, ProposalRequest
from self_nomad.intake.service import (
    IntakePreviewResult,
    IntakeService,
    IntakeSubmitResult,
    OperationSummary,
)

__all__ = [
    "IntakeOperation",
    "IntakePreviewResult",
    "IntakeService",
    "IntakeSource",
    "IntakeSubmitResult",
    "OperationSummary",
    "ProposalRequest",
    "load_proposal_request",
    "load_proposal_request_from_path",
    "load_proposal_request_from_stream",
]
