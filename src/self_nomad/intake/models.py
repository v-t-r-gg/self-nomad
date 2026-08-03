"""Version 1 agent proposal request contract."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from self_nomad.manifest.schema import validate_portable_path

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
# Allow tab, LF, CR; reject NUL and other C0 controls.
_DISALLOWED_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _reject_unsafe_text(value: str, *, field: str) -> str:
    if "\x00" in value:
        raise ValueError(f"{field} must not contain NUL characters")
    if _DISALLOWED_CONTROL.search(value):
        raise ValueError(f"{field} contains disallowed control characters")
    return value


def _validate_sha256(value: str | None) -> str | None:
    if value is None:
        return None
    if not SHA256_RE.fullmatch(value):
        raise ValueError("must be a lowercase 64-character hexadecimal SHA-256 digest")
    return value


class IntakeSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runtime: str = Field(min_length=1, max_length=128)
    agent_identifier: str | None = Field(default=None, max_length=256)
    correlation_id: str | None = Field(default=None, max_length=256)

    @field_validator("runtime", "agent_identifier", "correlation_id")
    @classmethod
    def safe_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _reject_unsafe_text(value, field="source field")


class IntakeOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["add", "replace", "delete"]
    path: str
    expected_before_sha256: str | None = None
    expected_after_sha256: str | None = None
    content: str | None = None

    @field_validator("path")
    @classmethod
    def portable_path(cls, value: str) -> str:
        return validate_portable_path(value)

    @field_validator("expected_before_sha256", "expected_after_sha256")
    @classmethod
    def sha256_hex(cls, value: str | None) -> str | None:
        return _validate_sha256(value)

    @field_validator("content")
    @classmethod
    def safe_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _reject_unsafe_text(value, field="content")

    @model_validator(mode="after")
    def operation_rules(self) -> IntakeOperation:
        if self.kind in {"add", "replace"} and self.content is None:
            raise ValueError("add and replace operations require content")
        if self.kind == "delete" and self.content is not None:
            raise ValueError("delete operations cannot have content")
        # content_source is intentionally not a field — agent requests must not
        # supply filesystem paths.
        return self

    def content_bytes(self) -> bytes | None:
        if self.content is None:
            return None
        return self.content.encode("utf-8")

    def content_sha256(self) -> str | None:
        data = self.content_bytes()
        if data is None:
            return None
        return hashlib.sha256(data).hexdigest()


class ProposalRequest(BaseModel):
    """Strict agent-facing proposal intake request (schema version 1)."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    request_id: str = Field(min_length=1, max_length=256)
    reason: str = Field(min_length=1, max_length=4096)
    target_branch: str | None = Field(default=None, min_length=1, max_length=256)
    source: IntakeSource
    operations: list[IntakeOperation] = Field(min_length=1)

    @field_validator("request_id", "reason", "target_branch")
    @classmethod
    def safe_text_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _reject_unsafe_text(value, field="request field")

    def canonical_digest(self) -> str:
        """Deterministic hash of the validated semantic request model."""
        payload = self.model_dump(mode="json")
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
