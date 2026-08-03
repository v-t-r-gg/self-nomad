"""Agent-facing proposal intake."""

from self_nomad.intake.loader import (
    load_proposal_request,
    load_proposal_request_from_path,
    load_proposal_request_from_stream,
)
from self_nomad.intake.models import (
    AddOperation,
    DeleteOperation,
    IntakeOperation,
    IntakeSource,
    ProposalRequest,
    ReplaceOperation,
)
from self_nomad.intake.service import (
    IntakePreviewResult,
    IntakeService,
    IntakeSubmitResult,
    OperationSummary,
)

__all__ = [
    "AddOperation",
    "DeleteOperation",
    "IntakeOperation",
    "IntakePreviewResult",
    "IntakeService",
    "IntakeSource",
    "IntakeSubmitResult",
    "OperationSummary",
    "ProposalRequest",
    "ReplaceOperation",
    "load_proposal_request",
    "load_proposal_request_from_path",
    "load_proposal_request_from_stream",
]
