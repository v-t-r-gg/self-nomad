"""Bounded MCP tool implementations for a fixed self repository."""

from __future__ import annotations

from typing import Any

from self_nomad import __version__
from self_nomad.adapters import default_registry
from self_nomad.application import SelfNomad
from self_nomad.domain import ProposalStatus
from self_nomad.errors import SelfNomadError
from self_nomad.intake.models import ProposalRequest
from self_nomad.mcp_server.errors import McpServerError, map_exception
from self_nomad.mcp_server.models import (
    ErrorItem,
    ProposalIdInput,
    ProposalListInput,
    ToolEnvelope,
    ValidateInput,
)
from self_nomad.mcp_server.sanitize import decode_cursor, encode_cursor, sanitize_proposal

EXPECTED_TOOL_NAMES: tuple[str, ...] = (
    "self_nomad_repository_status",
    "self_nomad_repository_validate",
    "self_nomad_intake_preview",
    "self_nomad_intake_submit",
    "self_nomad_proposal_list",
    "self_nomad_proposal_get",
    "self_nomad_proposal_validate",
)

FORBIDDEN_TOOL_SUBSTRINGS: tuple[str, ...] = (
    "approve",
    "apply",
    "reject",
    "restore",
    "import",
    "cleanup",
    "push",
    "execute",
)


def envelope(
    tool: str,
    *,
    ok: bool,
    result: dict[str, Any] | None = None,
    errors: list[ErrorItem] | None = None,
    warnings: list[object] | None = None,
) -> dict[str, Any]:
    payload = ToolEnvelope(
        tool=tool,
        ok=ok,
        result=result or {},
        warnings=warnings or [],
        errors=errors or [],
    )
    return payload.model_dump(mode="json")


def fail(tool: str, exc: BaseException) -> dict[str, Any]:
    code, message = map_exception(exc)
    return envelope(tool, ok=False, errors=[ErrorItem(code=code, message=message, path=None)])


class ToolContext:
    """Repository-scoped helpers used by MCP tool handlers."""

    def __init__(self, app: SelfNomad) -> None:
        self.app = app
        self.root = app.repository.root

    def status(self) -> dict[str, Any]:
        repo = self.app.repository
        manifest = repo.load_manifest()
        validation = repo.validate(strict=False)
        # Proposal listing must not create state dirs if none exist.
        counts: dict[str, int] = {status.value: 0 for status in ProposalStatus}
        try:
            records = self.app.proposals().store.list()
            for record in records:
                counts[record.status.value] = counts.get(record.status.value, 0) + 1
        except OSError:
            records = []
        branch = "unknown"
        head = "unknown"
        try:
            from self_nomad.git import GitBackend

            git = GitBackend(repo.root)
            branch = git.current_branch()
            head = git.head()
        except SelfNomadError:
            pass
        # Root is the resolved absolute path of the fixed server repository.
        # Documented sanitization: never rewrite via process CWD; never accept
        # a client-supplied path. Staging/worktree paths are never returned.
        return {
            "package_version": __version__,
            "repository": {
                "id": str(manifest.self.id),
                "name": manifest.self.name,
                "schema_version": manifest.schema_version,
                "root": str(self.root.resolve()),
            },
            "git": {"branch": branch, "head": head},
            "validation": {
                "valid": validation.valid,
                "finding_count": len(validation.findings),
                "content_digest": validation.content_digest,
            },
            "proposals": {"counts": counts, "total": sum(counts.values())},
            "adapters": default_registry().names(),
        }

    def validate_repository(self, data: ValidateInput) -> dict[str, Any]:
        result = self.app.repository.validate(strict=data.strict)
        return {
            "valid": result.valid,
            "content_digest": result.content_digest,
            "findings": [finding.model_dump(mode="json") for finding in result.findings],
            "validator_versions": result.validator_versions,
        }

    def intake_preview(self, request: ProposalRequest) -> dict[str, Any]:
        preview = self.app.intake().preview(request)
        return preview.model_dump(mode="json")

    def intake_submit(self, request: ProposalRequest) -> dict[str, Any]:
        result = self.app.intake().submit(request)
        return result.model_dump(mode="json")

    def proposal_list(self, data: ProposalListInput) -> dict[str, Any]:
        records = self.app.proposals().store.list()
        records = sorted(records, key=lambda item: item.proposal.id.hex)
        if data.status is not None:
            records = [item for item in records if item.status is data.status]
        start = 0
        if data.cursor:
            try:
                after = decode_cursor(data.cursor)
            except ValueError as exc:
                raise McpServerError(str(exc), code="MCP_INVALID_ARGUMENT") from exc
            for index, record in enumerate(records):
                if record.proposal.id.hex > after:
                    start = index
                    break
            else:
                start = len(records)
        page = records[start : start + data.limit]
        next_cursor = None
        if start + data.limit < len(records) and page:
            next_cursor = encode_cursor(page[-1].proposal.id)
        return {
            "items": [sanitize_proposal(item) for item in page],
            "next_cursor": next_cursor,
            "count": len(page),
        }

    def proposal_get(self, data: ProposalIdInput) -> dict[str, Any]:
        record = self.app.proposals().store.load(data.proposal_id)
        return sanitize_proposal(record)

    def proposal_validate(self, data: ProposalIdInput) -> dict[str, Any]:
        service = self.app.proposals()
        record = service.store.load(data.proposal_id)
        if record.status is ProposalStatus.VALIDATED:
            # Idempotent re-validation path for unchanged validated proposals.
            try:
                service.validate(data.proposal_id)
            except SelfNomadError:
                # Fall through: validate() may re-check and raise if stale.
                raise
            record = service.store.load(data.proposal_id)
            payload = sanitize_proposal(record)
            payload["revalidated"] = True
            return payload
        record = service.validate(data.proposal_id)
        payload = sanitize_proposal(record)
        payload["revalidated"] = False
        return payload


def call_tool(ctx: ToolContext, tool: str, handler: Any, *args: Any) -> dict[str, Any]:
    import logging

    try:
        result = handler(*args)
        return envelope(tool, ok=True, result=result)
    except Exception as exc:  # noqa: BLE001 - boundary mapping
        if isinstance(exc, McpServerError | SelfNomadError):
            return fail(tool, exc)
        # Unexpected: generic message only; diagnostic goes to stderr via logging.
        logging.getLogger("self_nomad.mcp").error(
            "tool %s internal error: %s: %s",
            tool,
            type(exc).__name__,
            exc,
        )
        return fail(tool, Exception("an internal error occurred"))
