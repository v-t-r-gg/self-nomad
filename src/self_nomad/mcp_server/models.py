"""Structured MCP tool request/response models."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from self_nomad.domain import ProposalStatus
from self_nomad.intake.models import ProposalRequest
from self_nomad.intake.service import IntakePreviewResult, IntakeSubmitResult


class ErrorItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str
    path: str | None = None


class ToolEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    tool: str
    ok: bool
    result: dict[str, Any] = Field(default_factory=dict)
    warnings: list[object] = Field(default_factory=list)
    errors: list[ErrorItem] = Field(default_factory=list)


class ValidateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strict: bool = True


class ProposalIdInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal_id: UUID


class ProposalListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ProposalStatus | None = None
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = None


# Re-export for schema documentation / tool typing.
__all__ = [
    "ErrorItem",
    "IntakePreviewResult",
    "IntakeSubmitResult",
    "ProposalIdInput",
    "ProposalListInput",
    "ProposalRequest",
    "ToolEnvelope",
    "ValidateInput",
]
