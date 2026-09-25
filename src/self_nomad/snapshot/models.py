"""Additive pack sidecar. Does not widen repository schema_version 1."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

PACK_FORMAT = "self-nomad-pack-v1"
PACK_SIDECAR = "self-nomad.pack.json"
PackProfile = Literal["specialist", "personal"]


class PackIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    name: str
    description: str | None = None


class PackPolicyHighlights(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approval_default: str
    scan_for_secrets: bool
    maximum_file_bytes: int


class PackSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    pack_format: Literal["self-nomad-pack-v1"] = "self-nomad-pack-v1"
    profile: PackProfile
    self: PackIdentity
    skill_format: str
    skills: list[str] = Field(default_factory=list)
    omitted: list[str] = Field(default_factory=list)
    policy: PackPolicyHighlights
    content_digest: str
    created_at: datetime
