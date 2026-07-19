from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from self_nomad.manifest.schema import validate_portable_path


class ProposalStatus(StrEnum):
    DRAFT = "draft"
    MATERIALIZED = "materialized"
    VALIDATED = "validated"
    APPROVED = "approved"
    APPLIED = "applied"
    REJECTED = "rejected"
    STALE = "stale"
    FAILED = "failed"


class Proposer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["human", "agent", "script"] = "human"
    identifier: str | None = None


class FileOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["add", "replace", "delete"]
    path: str
    expected_before_sha256: str | None = None
    expected_after_sha256: str | None = None
    content_source: str | None = None

    @model_validator(mode="after")
    def valid_operation(self) -> "FileOperation":
        validate_portable_path(self.path)
        if self.kind in {"add", "replace"} and self.content_source is None:
            raise ValueError("add and replace operations require content_source")
        if self.kind == "delete" and self.content_source is not None:
            raise ValueError("delete operations cannot have content_source")
        return self


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int = 1
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    repository_id: UUID
    base_commit: str
    target_branch: str
    source_adapter: str | None = None
    proposer: Proposer = Field(default_factory=Proposer)
    reason: str = Field(min_length=1, max_length=4096)
    operations: list[FileOperation] = Field(min_length=1)
    risk: Literal["low", "medium", "high", "critical"] = "medium"


class ProposalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal: Proposal
    status: ProposalStatus = ProposalStatus.DRAFT
    worktree: str | None = None
    branch: str | None = None
    proposal_commit: str | None = None
    content_digest: str | None = None
    validated_tree: str | None = None
    approved_tree: str | None = None
    approved_at: datetime | None = None
    approval_identifier: str | None = None
    rejection_reason: str | None = None
    applied_commit: str | None = None
