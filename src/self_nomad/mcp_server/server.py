"""Build the bounded self-nomad MCP server for a fixed repository root."""

from __future__ import annotations

import logging
from importlib.resources import files
from pathlib import Path
from typing import Any
from uuid import UUID

from mcp.server import MCPServer
from mcp_types import ToolAnnotations

from self_nomad import __version__
from self_nomad.application import SelfNomad
from self_nomad.domain import ProposalStatus
from self_nomad.errors import RepositoryNotFoundError, SelfNomadError
from self_nomad.intake.models import ProposalRequest
from self_nomad.mcp_server.errors import (
    McpConfigurationError,
    McpInvalidArgumentError,
    McpRepositoryUnavailableError,
)
from self_nomad.mcp_server.middleware import EnvelopeBoundaryMiddleware
from self_nomad.mcp_server.models import ProposalIdInput, ProposalListInput, ValidateInput
from self_nomad.mcp_server.tools import (
    EXPECTED_TOOL_NAMES,
    ToolContext,
    call_tool,
    fail,
)

logger = logging.getLogger("self_nomad.mcp")


def open_fixed_repository(repo: Path) -> SelfNomad:
    try:
        path = repo.expanduser().resolve(strict=True)
    except OSError as exc:
        raise McpRepositoryUnavailableError(
            "configured repository path is not available"
        ) from exc
    if not path.is_dir():
        raise McpRepositoryUnavailableError("repository path must be a directory")
    try:
        return SelfNomad.open(path)
    except (RepositoryNotFoundError, SelfNomadError) as exc:
        raise McpRepositoryUnavailableError(
            "no self-nomad repository found at the configured path"
        ) from exc


def build_server(repo: Path) -> MCPServer:
    """Create an MCPServer bound to a single absolute self repository."""
    app = open_fixed_repository(repo)
    ctx = ToolContext(app)

    # Single public version source (installed metadata or source-tree sentinel).
    server = MCPServer(
        name="self-nomad",
        title="self-nomad",
        description=(
            "Bounded local MCP surface for inspecting a portable agent self "
            "repository and submitting isolated proposals. Submission never "
            "approves or applies changes to the target branch."
        ),
        version=__version__,
        instructions=(
            "Use self_nomad_intake_preview then self_nomad_intake_submit to create "
            "isolated proposals. Approval and apply are operator CLI operations "
            "outside this server. The managed repository root is fixed for the "
            "server lifetime; tool inputs never accept a repository path."
        ),
    )

    # Self-owned registration accounting (no private SDK managers).
    registered: list[str] = []

    def _register(name: str) -> None:
        if name not in EXPECTED_TOOL_NAMES:
            raise McpConfigurationError(
                f"refusing to register tool outside the allow-list: {name}"
            )
        if name in registered:
            raise McpConfigurationError(f"duplicate tool registration: {name}")
        registered.append(name)

    _register("self_nomad_repository_status")

    @server.tool(
        name="self_nomad_repository_status",
        description=(
            "Read-only status for the fixed self repository (identity, Git HEAD, "
            "validation summary, proposal counts, adapters). Does not create "
            "proposal state directories when none exist."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        structured_output=True,
    )
    def repository_status() -> dict[str, Any]:
        return call_tool(ctx, "self_nomad_repository_status", ctx.status)

    _register("self_nomad_repository_validate")

    @server.tool(
        name="self_nomad_repository_validate",
        description=(
            "Run structural repository validation. Repository tests remain "
            "disabled by policy."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        structured_output=True,
    )
    def repository_validate(strict: bool = True) -> dict[str, Any]:
        return call_tool(
            ctx,
            "self_nomad_repository_validate",
            ctx.validate_repository,
            ValidateInput(strict=strict),
        )

    _register("self_nomad_intake_preview")

    @server.tool(
        name="self_nomad_intake_preview",
        description=(
            "Zero-write preview of a ProposalRequest v1. Never creates proposals "
            "or changes the target branch. Inline content is omitted from results."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        structured_output=True,
    )
    def intake_preview(request: ProposalRequest) -> dict[str, Any]:
        return call_tool(ctx, "self_nomad_intake_preview", ctx.intake_preview, request)

    _register("self_nomad_intake_submit")

    @server.tool(
        name="self_nomad_intake_submit",
        description=(
            "Submit an idempotent ProposalRequest v1 and materialize an isolated "
            "proposal. May create a pending receipt, stage UTF-8 content, and "
            "return an existing proposal for the same request_id. Does not "
            "validate, approve, apply, reject, restore, or update the target branch."
        ),
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        structured_output=True,
    )
    def intake_submit(request: ProposalRequest) -> dict[str, Any]:
        return call_tool(ctx, "self_nomad_intake_submit", ctx.intake_submit, request)

    _register("self_nomad_proposal_list")

    @server.tool(
        name="self_nomad_proposal_list",
        description=(
            "List sanitized proposal summaries with optional status filter, "
            "deterministic ordering, and opaque cursor pagination. Empty state "
            "does not create directories."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        structured_output=True,
    )
    def proposal_list(
        status: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        status_enum: ProposalStatus | None = None
        if status is not None:
            try:
                status_enum = ProposalStatus(status)
            except ValueError:
                return fail(
                    "self_nomad_proposal_list",
                    McpInvalidArgumentError("unknown proposal status", path="status"),
                )
        try:
            payload = ProposalListInput(status=status_enum, limit=limit, cursor=cursor)
        except Exception:  # noqa: BLE001 - pydantic validation boundary
            return fail(
                "self_nomad_proposal_list",
                McpInvalidArgumentError("invalid tool arguments"),
            )
        return call_tool(ctx, "self_nomad_proposal_list", ctx.proposal_list, payload)

    _register("self_nomad_proposal_get")

    @server.tool(
        name="self_nomad_proposal_get",
        description=(
            "Fetch a sanitized proposal review record by id. Omits content_source, "
            "inline content, and absolute staging/worktree paths."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        structured_output=True,
    )
    def proposal_get(proposal_id: UUID) -> dict[str, Any]:
        return call_tool(
            ctx,
            "self_nomad_proposal_get",
            ctx.proposal_get,
            ProposalIdInput(proposal_id=proposal_id),
        )

    _register("self_nomad_proposal_validate")

    @server.tool(
        name="self_nomad_proposal_validate",
        description=(
            "Strictly validate a materialized proposal (complete-tree verification, "
            "declared-diff binding, secret scanning). Idempotent for an already "
            "validated unchanged proposal. Does not approve or apply."
        ),
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        structured_output=True,
    )
    def proposal_validate(proposal_id: UUID) -> dict[str, Any]:
        return call_tool(
            ctx,
            "self_nomad_proposal_validate",
            ctx.proposal_validate,
            ProposalIdInput(proposal_id=proposal_id),
        )

    @server.resource(
        "self-nomad://schemas/proposal-request/v1",
        name="proposal-request-v1",
        description="Packaged ProposalRequest v1 JSON Schema.",
        mime_type="application/schema+json",
    )
    def proposal_request_schema() -> str:
        return (
            files("self_nomad.schemas")
            .joinpath("proposal-request-v1.schema.json")
            .read_text(encoding="utf-8")
        )

    if sorted(registered) != sorted(EXPECTED_TOOL_NAMES):
        logger.error("tool registry mismatch: %s != %s", registered, list(EXPECTED_TOOL_NAMES))
        raise McpConfigurationError("MCP tool registry does not match the expected allow-list")

    # Enforce envelope contract for recognized-tool argument failures.
    server.middleware.append(EnvelopeBoundaryMiddleware())

    return server
