"""Strict UTF-8 JSON loading for proposal intake requests."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from self_nomad.errors import (
    IntakeDuplicateKeyError,
    IntakeInvalidJsonError,
    IntakeInvalidUtf8Error,
    IntakeRequestTooLargeError,
    IntakeSchemaInvalidError,
    IntakeSchemaUnsupportedError,
)
from self_nomad.intake.models import ProposalRequest

DEFAULT_MAXIMUM_REQUEST_BYTES = 4_194_304


class _DuplicateKeyDetector(dict[str, Any]):
    def __init__(self, pairs: list[tuple[str, Any]]) -> None:
        super().__init__()
        for key, value in pairs:
            if key in self:
                raise IntakeDuplicateKeyError(
                    f"duplicate JSON object key: {key!r}",
                    code="INTAKE_DUPLICATE_KEY",
                )
            self[key] = value


def _decode_utf8(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IntakeInvalidUtf8Error(
            "request body is not valid UTF-8",
            code="INTAKE_INVALID_UTF8",
        ) from exc


def _parse_json_object(text: str) -> Mapping[str, Any]:
    try:
        data = json.loads(text, object_pairs_hook=_DuplicateKeyDetector)
    except IntakeDuplicateKeyError:
        raise
    except json.JSONDecodeError as exc:
        raise IntakeInvalidJsonError(
            "request body is not valid JSON",
            code="INTAKE_INVALID_JSON",
        ) from exc
    if not isinstance(data, dict):
        raise IntakeSchemaInvalidError(
            "request root must be a JSON object",
            code="INTAKE_SCHEMA_INVALID",
        )
    return data


def _validate_request(data: Mapping[str, Any]) -> ProposalRequest:
    version = data.get("schema_version")
    if version is not None and version != 1:
        raise IntakeSchemaUnsupportedError(
            f"unsupported intake schema_version: {version!r}",
            code="INTAKE_SCHEMA_UNSUPPORTED",
        )
    try:
        return ProposalRequest.model_validate(data)
    except ValidationError as exc:
        # Avoid echoing inline file content from validation context.
        messages: list[str] = []
        for error in exc.errors():
            loc = ".".join(str(part) for part in error.get("loc", ()))
            msg = error.get("msg", "invalid")
            messages.append(f"{loc}: {msg}" if loc else msg)
        summary = "; ".join(messages[:8]) or "request failed schema validation"
        raise IntakeSchemaInvalidError(summary, code="INTAKE_SCHEMA_INVALID") from exc


def load_proposal_request(
    raw: bytes,
    *,
    maximum_request_bytes: int = DEFAULT_MAXIMUM_REQUEST_BYTES,
) -> ProposalRequest:
    """Parse and validate a proposal request from UTF-8 JSON bytes."""
    if len(raw) > maximum_request_bytes:
        raise IntakeRequestTooLargeError(
            f"request exceeds maximum_request_bytes ({maximum_request_bytes})",
            code="INTAKE_REQUEST_TOO_LARGE",
        )
    text = _decode_utf8(raw)
    data = _parse_json_object(text)
    return _validate_request(data)


def load_proposal_request_from_path(
    path: Path,
    *,
    maximum_request_bytes: int = DEFAULT_MAXIMUM_REQUEST_BYTES,
) -> ProposalRequest:
    """Load a request from a regular file without following symlinks."""
    if path.is_symlink():
        raise IntakeSchemaInvalidError(
            "request path must not be a symlink",
            code="INTAKE_SCHEMA_INVALID",
        )
    if not path.is_file():
        raise IntakeSchemaInvalidError(
            "request path must be a regular file",
            code="INTAKE_SCHEMA_INVALID",
        )
    size = path.stat().st_size
    if size > maximum_request_bytes:
        raise IntakeRequestTooLargeError(
            f"request exceeds maximum_request_bytes ({maximum_request_bytes})",
            code="INTAKE_REQUEST_TOO_LARGE",
        )
    return load_proposal_request(
        path.read_bytes(),
        maximum_request_bytes=maximum_request_bytes,
    )


def load_proposal_request_from_stream(
    stream: Any,
    *,
    maximum_request_bytes: int = DEFAULT_MAXIMUM_REQUEST_BYTES,
) -> ProposalRequest:
    """Read stdin or any binary stream incrementally up to limit + 1 byte."""
    chunks: list[bytes] = []
    total = 0
    limit = maximum_request_bytes + 1
    while total < limit:
        chunk = stream.read(min(65_536, limit - total))
        if not chunk:
            break
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8")
        chunks.append(chunk)
        total += len(chunk)
    raw = b"".join(chunks)
    if len(raw) > maximum_request_bytes:
        raise IntakeRequestTooLargeError(
            f"request exceeds maximum_request_bytes ({maximum_request_bytes})",
            code="INTAKE_REQUEST_TOO_LARGE",
        )
    return load_proposal_request(raw, maximum_request_bytes=maximum_request_bytes)
