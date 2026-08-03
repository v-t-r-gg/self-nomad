"""Version 1 agent proposal request contract."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from self_nomad.manifest.schema import validate_portable_path

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
# Inline content: allow tab, LF, CR; reject NUL and other C0 controls.
_CONTENT_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
# Identifiers / branches: reject all C0 controls including tab/LF/CR.
_IDENTIFIER_CONTROL = re.compile(r"[\x00-\x1f]")
# Machine-safe durable request IDs (no whitespace/control).
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+=@/-]{0,255}$")
# Schema-friendly portable path pattern (no look-around; full checks in validator).
# Segments are non-empty relative names without '/' or NUL.
PORTABLE_PATH_SCHEMA = r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$"
# Reason may be multiline; forbid NUL and other unsafe C0 except tab/LF/CR.
_REASON_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _reject_identifier(value: str, *, field: str) -> str:
    if _IDENTIFIER_CONTROL.search(value):
        raise ValueError(f"{field} must not contain control characters")
    return value


def _reject_content(value: str) -> str:
    if _CONTENT_CONTROL.search(value):
        raise ValueError("content contains disallowed control characters")
    return value


def _reject_reason(value: str) -> str:
    if _REASON_CONTROL.search(value):
        raise ValueError("reason contains disallowed control characters")
    return value


def _validate_sha256(value: str | None) -> str | None:
    if value is None:
        return None
    if not SHA256_RE.fullmatch(value):
        raise ValueError("must be a lowercase 64-character hexadecimal SHA-256 digest")
    return value


class IntakeSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runtime: str = Field(
        min_length=1,
        max_length=128,
        description="Runtime or integration name that produced the request.",
    )
    agent_identifier: str | None = Field(
        default=None,
        max_length=256,
        description="Optional agent instance identifier within the runtime.",
    )
    correlation_id: str | None = Field(
        default=None,
        max_length=256,
        description="Optional caller correlation token for tracing.",
    )

    @field_validator("runtime", "agent_identifier", "correlation_id")
    @classmethod
    def safe_identifiers(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _reject_identifier(value, field="source field")


class _PathMixin(BaseModel):
    path: str = Field(
        min_length=1,
        max_length=1024,
        description="Repository-relative POSIX path for a portable artifact.",
        pattern=PORTABLE_PATH_SCHEMA,
    )

    @field_validator("path")
    @classmethod
    def portable_path(cls, value: str) -> str:
        return validate_portable_path(value)


class AddOperation(_PathMixin):
    """Add a new regular file that must not already exist on the target branch."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["add"] = Field(description="Create a new file at path.")
    content: str = Field(
        description="Inline UTF-8 file content. Tab, LF, and CR are allowed.",
    )
    expected_after_sha256: str | None = Field(
        default=None,
        description="Optional SHA-256 of the UTF-8 content bytes.",
        pattern=SHA256_RE.pattern,
    )

    @field_validator("content")
    @classmethod
    def safe_content(cls, value: str) -> str:
        return _reject_content(value)

    @field_validator("expected_after_sha256")
    @classmethod
    def sha256_hex(cls, value: str | None) -> str | None:
        return _validate_sha256(value)

    def content_bytes(self) -> bytes:
        return self.content.encode("utf-8")

    def content_sha256(self) -> str:
        return hashlib.sha256(self.content_bytes()).hexdigest()


class ReplaceOperation(_PathMixin):
    """Replace an existing regular file blob on the target branch."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["replace"] = Field(description="Replace an existing file at path.")
    content: str = Field(
        description="Inline UTF-8 file content. Tab, LF, and CR are allowed.",
    )
    expected_before_sha256: str | None = Field(
        default=None,
        description="Optional SHA-256 of the current target-branch blob.",
        pattern=SHA256_RE.pattern,
    )
    expected_after_sha256: str | None = Field(
        default=None,
        description="Optional SHA-256 of the UTF-8 content bytes.",
        pattern=SHA256_RE.pattern,
    )

    @field_validator("content")
    @classmethod
    def safe_content(cls, value: str) -> str:
        return _reject_content(value)

    @field_validator("expected_before_sha256", "expected_after_sha256")
    @classmethod
    def sha256_hex(cls, value: str | None) -> str | None:
        return _validate_sha256(value)

    def content_bytes(self) -> bytes:
        return self.content.encode("utf-8")

    def content_sha256(self) -> str:
        return hashlib.sha256(self.content_bytes()).hexdigest()


class DeleteOperation(_PathMixin):
    """Delete an existing regular file blob on the target branch."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["delete"] = Field(description="Delete an existing file at path.")
    expected_before_sha256: str | None = Field(
        default=None,
        description="Optional SHA-256 of the current target-branch blob.",
        pattern=SHA256_RE.pattern,
    )

    @field_validator("expected_before_sha256")
    @classmethod
    def sha256_hex(cls, value: str | None) -> str | None:
        return _validate_sha256(value)

    def content_bytes(self) -> None:
        return None

    def content_sha256(self) -> None:
        return None


IntakeOperation = Annotated[
    AddOperation | ReplaceOperation | DeleteOperation,
    Field(discriminator="kind"),
]


class ProposalRequest(BaseModel):
    """Strict agent-facing proposal intake request (schema version 1)."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = Field(
        description="Intake request schema version. Only 1 is supported.",
    )
    request_id: str = Field(
        min_length=1,
        max_length=256,
        pattern=REQUEST_ID_RE.pattern,
        description=(
            "Caller-chosen durable idempotency key. Machine-safe characters only; "
            "retries with the same id and payload reuse one proposal."
        ),
    )
    reason: str = Field(
        min_length=1,
        max_length=4096,
        description="Human-readable rationale for the proposed change.",
    )
    target_branch: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
        description="Optional Git branch to target; defaults to the current branch.",
    )
    source: IntakeSource = Field(description="Provenance of the requesting agent or tool.")
    operations: list[IntakeOperation] = Field(
        min_length=1,
        description="Ordered portable file operations. Paths must be unique.",
    )

    @field_validator("request_id")
    @classmethod
    def safe_request_id(cls, value: str) -> str:
        if not REQUEST_ID_RE.fullmatch(value):
            raise ValueError("request_id has an invalid machine-safe pattern")
        return _reject_identifier(value, field="request_id")

    @field_validator("reason")
    @classmethod
    def safe_reason(cls, value: str) -> str:
        return _reject_reason(value)

    @field_validator("target_branch")
    @classmethod
    def safe_branch(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _reject_identifier(value, field="target_branch")

    def canonical_bytes(self) -> bytes:
        """Deterministic UTF-8 serialization used for digests and size checks."""
        payload = self.model_dump(mode="json")
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    def canonical_digest(self) -> str:
        """Deterministic hash of the validated semantic request model."""
        return hashlib.sha256(self.canonical_bytes()).hexdigest()
