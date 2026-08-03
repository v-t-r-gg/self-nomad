"""Safe validation of MCP tool arguments before SDK type coercion.

Produces envelope-ready error items without echoing invalid values, inline
content, Pydantic ``input_value`` text, or caller-controlled property names.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import ValidationError

from self_nomad.domain import ProposalStatus
from self_nomad.intake.models import ProposalRequest
from self_nomad.mcp_server.errors import McpInvalidArgumentError
from self_nomad.mcp_server.models import ErrorItem, ProposalListInput
from self_nomad.mcp_server.tools import EXPECTED_TOOL_NAMES

# Per-tool allowed top-level argument keys (flat JSON shapes for agents).
TOOL_ARGUMENT_KEYS: dict[str, frozenset[str]] = {
    "self_nomad_repository_status": frozenset(),
    "self_nomad_repository_validate": frozenset({"strict"}),
    "self_nomad_intake_preview": frozenset({"request"}),
    "self_nomad_intake_submit": frozenset({"request"}),
    "self_nomad_proposal_list": frozenset({"status", "limit", "cursor"}),
    "self_nomad_proposal_get": frozenset({"proposal_id"}),
    "self_nomad_proposal_validate": frozenset({"proposal_id"}),
}

# Known nested schema field names only (never emit caller-supplied keys).
_REQUEST_FIELDS = frozenset(
    {
        "schema_version",
        "request_id",
        "reason",
        "target_branch",
        "source",
        "operations",
    }
)
_SOURCE_FIELDS = frozenset({"runtime", "agent_identifier", "correlation_id"})
_OPERATION_FIELDS = frozenset(
    {
        "kind",
        "path",
        "content",
        "expected_before_sha256",
        "expected_after_sha256",
    }
)
_LIST_FIELDS = frozenset({"status", "limit", "cursor"})
_GENERIC_ROOT = "$"


def _error(message: str, *, path: str | None = None) -> ErrorItem:
    return ErrorItem(code="MCP_INVALID_ARGUMENT", message=message, path=path)


def safe_path_from_loc(
    loc: tuple[Any, ...],
    *,
    base: str | None = None,
    schema: str = "request",
) -> str | None:
    """Build a path from known field names and numeric indexes only.

    Unknown property names supplied by the caller are never serialized. When an
    unknown segment appears, the path stops at the last known parent (or ``$``
    for a completely unknown top-level name).
    """
    parts: list[str] = []
    if base is not None:
        parts.append(base)

    # Context stack tracks which known object schema we are inside.
    # After ``base="request"`` we start in the request schema.
    context: str | None = base if base in {"request"} else None
    if schema == "list" and base is None:
        context = "list"
    elif schema == "tool" and base is None:
        context = "tool"

    for item in loc:
        if isinstance(item, int):
            # List indexes are safe (not caller-controlled names).
            parts.append(str(item))
            continue
        if not isinstance(item, str):
            break

        if context == "request":
            if item not in _REQUEST_FIELDS:
                break
            parts.append(item)
            if item == "source":
                context = "source"
            elif item == "operations":
                context = "operation"
            continue

        if context == "source":
            if item not in _SOURCE_FIELDS:
                break
            parts.append(item)
            continue

        if context == "operation":
            if item not in _OPERATION_FIELDS:
                break
            parts.append(item)
            continue

        if context == "list":
            if item not in _LIST_FIELDS:
                break
            parts.append(item)
            continue

        if context == "tool":
            # Flat tool args without a request envelope.
            allowed = _LIST_FIELDS | {"strict", "proposal_id", "request"}
            if item not in allowed:
                break
            parts.append(item)
            if item == "request":
                context = "request"
            continue

        # No context: only accept known root tokens.
        if item == "request":
            parts.append(item)
            context = "request"
            continue
        if item in _LIST_FIELDS | {"strict", "proposal_id"}:
            parts.append(item)
            continue
        # Unknown top-level name.
        return _GENERIC_ROOT

    if not parts:
        return _GENERIC_ROOT if base is None else base
    return ".".join(parts)


def _validation_errors(
    exc: ValidationError,
    *,
    base: str | None = None,
    schema: str = "request",
) -> list[ErrorItem]:
    """Map Pydantic errors to safe items (no input_value, no raw content)."""
    items: list[ErrorItem] = []
    for err in exc.errors():
        path = safe_path_from_loc(tuple(err.get("loc", ())), base=base, schema=schema)
        err_type = str(err.get("type", ""))
        if err_type == "extra_forbidden":
            items.append(_error("unexpected field", path=path))
        elif err_type == "missing":
            items.append(_error("required field missing", path=path))
        elif err_type in {"literal_error", "enum"}:
            items.append(_error("unsupported or invalid field value", path=path))
        elif err_type in {"uuid_parsing", "uuid_type"}:
            items.append(_error("invalid proposal_id", path=path or "proposal_id"))
        elif err_type in {
            "greater_than_equal",
            "less_than_equal",
            "int_parsing",
            "int_type",
        }:
            items.append(_error("invalid numeric field", path=path))
        elif err_type in {"string_type", "string_too_short", "string_too_long"}:
            items.append(_error("invalid string field", path=path))
        elif path and path.endswith("schema_version"):
            items.append(_error("unsupported schema version", path=path))
        else:
            items.append(_error("invalid field", path=path))
    if not items:
        items.append(_error("invalid tool arguments"))
    return items


def validate_tool_arguments(tool: str, arguments: dict[str, Any] | None) -> list[ErrorItem] | None:
    """Return a list of public errors if *arguments* are invalid; else ``None``.

    Unknown tool names return ``None`` so the MCP protocol can reject them.
    """
    if tool not in EXPECTED_TOOL_NAMES:
        return None

    args = arguments if isinstance(arguments, dict) else {}
    allowed = TOOL_ARGUMENT_KEYS[tool]
    unknown = set(args) - allowed
    if unknown:
        # Never put the caller-supplied key name in the response path.
        return [_error("unexpected argument", path=_GENERIC_ROOT)]

    if tool == "self_nomad_repository_status":
        return None

    if tool == "self_nomad_repository_validate":
        if "strict" in args and not isinstance(args["strict"], bool):
            return [_error("invalid field", path="strict")]
        return None

    if tool in {"self_nomad_proposal_get", "self_nomad_proposal_validate"}:
        if "proposal_id" not in args:
            return [_error("required field missing", path="proposal_id")]
        raw = args["proposal_id"]
        try:
            UUID(str(raw))
        except (ValueError, TypeError, AttributeError):
            return [_error("invalid proposal_id", path="proposal_id")]
        return None

    if tool == "self_nomad_proposal_list":
        if "status" in args and args["status"] is not None:
            try:
                ProposalStatus(args["status"])
            except (ValueError, TypeError):
                return [_error("unknown proposal status", path="status")]
        if "limit" in args:
            limit = args["limit"]
            if not isinstance(limit, int) or isinstance(limit, bool) or not (1 <= limit <= 200):
                return [_error("limit out of range", path="limit")]
        if "cursor" in args and args["cursor"] is not None:
            if not isinstance(args["cursor"], str):
                return [_error("invalid pagination cursor", path="cursor")]
            from self_nomad.mcp_server.sanitize import decode_cursor

            try:
                decode_cursor(args["cursor"])
            except ValueError:
                return [_error("invalid pagination cursor", path="cursor")]
        try:
            status_enum = None
            if args.get("status") is not None:
                status_enum = ProposalStatus(args["status"])
            ProposalListInput(
                status=status_enum,
                limit=args.get("limit", 50),
                cursor=args.get("cursor"),
            )
        except ValidationError as exc:
            return _validation_errors(exc, schema="list")
        except (ValueError, TypeError):
            return [_error("invalid tool arguments")]
        return None

    if tool in {"self_nomad_intake_preview", "self_nomad_intake_submit"}:
        if "request" not in args:
            return [_error("required field missing", path="request")]
        request = args["request"]
        if not isinstance(request, dict):
            return [_error("invalid field", path="request")]
        try:
            ProposalRequest.model_validate(request)
        except ValidationError as exc:
            return _validation_errors(exc, base="request", schema="request")
        return None

    return [_error("invalid tool arguments")]


def ensure_valid_arguments(tool: str, arguments: dict[str, Any] | None) -> None:
    """Raise :class:`McpInvalidArgumentError` when arguments are invalid."""
    errors = validate_tool_arguments(tool, arguments)
    if errors:
        first = errors[0]
        raise McpInvalidArgumentError(first.message, path=first.path)
